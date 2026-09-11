"""Card-based transfers using the existing toolbar and verified backup operations."""
from PySide6.QtCore import QObject, QEvent, Qt, QThread, Signal, Slot, QTimer
from PySide6.QtWidgets import QFrame, QWidget, QHBoxLayout, QLabel, QPushButton, QMessageBox
from shiboken6 import isValid

from .app_options import load_options, options_snapshot
from .backup_policies import record_locked
from .backup_transaction import backup_busy
from .light_controls import LIGHT_CONTROLS_STYLE


def visible_items(window, direction):
    cards = getattr(window, '_livery_grid_cards' if direction == 'game' else '_fh6_backup_cards', [])
    items = []
    seen = set()
    for card in cards or []:
        if not isValid(card) or not card.isVisible():
            continue
        record = (window._record_for_content_key('livery', str(card.property('annotationKey') or ''))
                  if direction == 'game' else card.property('backupRecord'))
        if record is None:
            continue
        key = str(record.container_path.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            items.append((card, record, dict(getattr(card, '_fh6_backup_entry', {}))))
    return items


def choose_policy(window, count, *, selection=True, cut_allowed=True):
    box = QMessageBox(window)
    box.setStyleSheet(LIGHT_CONTROLS_STYLE)
    box.setWindowTitle('내보내기')
    box.setText(f'{count}개 항목을 내보냅니다.\n복사는 원본을 유지하며, 잘라내기는 검증 완료 후 원본을 삭제합니다.\n잠긴 항목의 원본은 유지됩니다.')
    copy = box.addButton('복사', QMessageBox.ButtonRole.AcceptRole)
    cut = box.addButton('잘라내기', QMessageBox.ButtonRole.DestructiveRole)
    cut.setEnabled(cut_allowed and not load_options().disable_export_cut)
    select = box.addButton('선택', QMessageBox.ButtonRole.ActionRole) if selection else None
    box.addButton('취소', QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(copy)
    box.exec()
    clicked = box.clickedButton()
    if clicked is copy:
        return 'copy'
    if clicked is cut and cut.isEnabled():
        return 'cut'
    if select is not None and clicked is select:
        return 'select'
    return 'cancel'


class CardSelection(QObject):
    def __init__(self, window, direction, items):
        super().__init__(window)
        self.window, self.direction, self.items = window, direction, items
        self.selected = set()
        self.overlays = []
        window._fh6_card_selection = self
        button = window.livery_export_visible_button if direction == 'game' else window.backup_export_button
        from .v1_3_4_card_features_patch import _find_layout_containing
        layout = _find_layout_containing(button.parentWidget().layout(), button)
        self.bar = QWidget(button.parentWidget())
        self.bar.setStyleSheet(LIGHT_CONTROLS_STYLE)
        row = QHBoxLayout(self.bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.count = QLabel('0개 선택')
        self.done = QPushButton('선택 완료')
        self.done.setEnabled(False)
        cancel = QPushButton('취소')
        row.addWidget(self.count)
        row.addWidget(self.done)
        row.addWidget(cancel)
        layout.addWidget(self.bar)
        self.button = button
        button.setEnabled(False)
        self.done.clicked.connect(self.finish)
        cancel.clicked.connect(self.cancel)
        for index, (card, _, _) in enumerate(items):
            overlay = QFrame(card)
            overlay.setObjectName('fh6TransferSelection')
            overlay.setProperty('selectionIndex', index)
            overlay.setCursor(Qt.CursorShape.PointingHandCursor)
            overlay.setGeometry(card.rect())
            overlay.installEventFilter(self)
            card.installEventFilter(self)
            self.overlays.append(overlay)
            self.decorate(index)
            overlay.show()
            overlay.raise_()
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.validate)
        self.timer.start()

    def decorate(self, index):
        color = '#7048f5' if index in self.selected else 'transparent'
        self.overlays[index].setStyleSheet(
            f'QFrame#fh6TransferSelection {{background:transparent; border:2px solid {color}; border-radius:12px;}}')

    def eventFilter(self, watched, event):
        index = watched.property('selectionIndex')
        if index is not None and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if index in self.selected:
                    self.selected.remove(index)
                else:
                    self.selected.add(index)
                self.decorate(index)
                self.count.setText(f'{len(self.selected)}개 선택')
                self.done.setEnabled(bool(self.selected))
                return True
        if index is not None and event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            return True
        if event.type() == QEvent.Type.Resize:
            for i, (card, _, _) in enumerate(self.items):
                if watched is card:
                    self.overlays[i].setGeometry(card.rect())
        return False

    @Slot()
    def validate(self):
        # A filter, tab switch or rebuild invalidates the selection snapshot.
        if any(not isValid(card) or not card.isVisible() for card, _, _ in self.items):
            self.cancel()

    def cleanup(self):
        self.timer.stop()
        for (card, _, _), overlay in zip(self.items, self.overlays):
            if isValid(card):
                card.removeEventFilter(self)
            if isValid(overlay):
                overlay.hide()
                overlay.deleteLater()
        if isValid(self.button):
            self.button.setEnabled(True)
        self.bar.hide()
        self.bar.deleteLater()
        self.window._fh6_card_selection = None
        self.deleteLater()

    @Slot()
    def cancel(self):
        self.cleanup()

    @Slot()
    def finish(self):
        items = [self.items[i] for i in sorted(self.selected)
                 if isValid(self.items[i][0]) and self.items[i][0].isVisible()]
        window, direction = self.window, self.direction
        self.cleanup()
        if items:
            policy = choose_policy(window, len(items), selection=False,
                                   cut_allowed=any(not record_locked(window, r) for _, r, _ in items))
            execute_transfer(window, direction, items, policy)


class ImportBatch(QThread):
    result_ready = Signal(object)

    def __init__(self, window, root, save_root, version, items):
        super().__init__(window)
        self.root, self.save_root, self.version, self.items = root, save_root, version, items

    def run(self):
        from .v1_3_4_backup_import_refinement_patch import import_backup_entry
        succeeded, deleted, failures = 0, 0, []
        with options_snapshot():
            for name, entry, cut in self.items:
                try:
                    result = import_backup_entry(self.root, entry, self.save_root, self.version,
                        delete_source=cut and not load_options().disable_export_cut)
                    succeeded += 1
                    deleted += int(result.source_deleted)
                except Exception as exc:
                    failures.append(f'{name}: {exc}')
        self.result_ready.emit((succeeded, deleted, failures))


class ImportBatchUi(QObject):
    def __init__(self, window, worker):
        super().__init__(window)
        self.window, self.worker, self.result = window, worker, None
        worker.result_ready.connect(self.received)
        worker.finished.connect(self.finished)

    @Slot(object)
    def received(self, result):
        self.result = result

    @Slot()
    def finished(self):
        window = self.window
        window._fh6_import_running = False
        window._end_busy()
        window._fh6_backup_presence_cache = ('', set(), set())
        from . import v1_3_4_backup_export_patch as backup
        backup._rebuild_backup_cards(window)
        succeeded, deleted, failures = self.result or (0, 0, ['작업 결과를 받지 못했습니다.'])
        text = f'복원 {succeeded}개 · 백업 원본 삭제 {deleted}개 · 실패 {len(failures)}개'
        window._show_status(text, 8000)
        if failures:
            QMessageBox.warning(window, '내보내기 결과', text + '\n\n' + '\n'.join(failures))
        else:
            QMessageBox.information(window, '내보내기 완료', text)
        window._fh6_import_batch = None
        self.worker.deleteLater()
        self.deleteLater()
        window.refresh_scan()


def execute_transfer(window, direction, items, policy):
    if policy not in ('copy', 'cut') or backup_busy(window):
        return
    if policy == 'cut' and load_options().disable_export_cut:
        return
    from . import v1_3_4_backup_export_patch as backup
    if direction == 'game':
        window._fh6_transfer_policy = policy
        try:
            backup._request_export(window, [record for _, record, _ in items])
        finally:
            window._fh6_transfer_policy = None
        return
    from .v1_3_4_backup_import_refinement_patch import _import_context, resolve_import_targets
    root = backup._backup_root(window)
    if root is None or not backup._backup_path_is_safe(window, root):
        return
    try:
        save_root, version = _import_context(window)
        resolve_import_targets(save_root, version)
    except Exception as exc:
        QMessageBox.warning(window, '들여오기 준비 실패', str(exc))
        return
    payload = [(record.header.name or record.container_name, entry,
                policy == 'cut' and not record_locked(window, record)) for _, record, entry in items]
    window._fh6_import_running = True
    window._begin_busy('들여오는 중')
    worker = ImportBatch(window, root, save_root, version, payload)
    bridge = ImportBatchUi(window, worker)
    window._fh6_import_batch = bridge
    worker.start()


def request_transfer(window, direction):
    if backup_busy(window) or getattr(window, '_fh6_card_selection', None):
        return
    thread = getattr(window, '_scan_thread', None)
    if thread is not None and thread.isRunning():
        window._show_status('스캔이 끝난 뒤 다시 시도해 주세요.', 4000)
        return
    items = visible_items(window, direction)
    if not items:
        window._show_status('현재 목록에 내보낼 항목이 없습니다.', 4000)
        return
    policy = choose_policy(window, len(items),
                           cut_allowed=any(not record_locked(window, record) for _, record, _ in items))
    # Modal dialogs can process refresh events; discard stale card snapshots.
    if backup_busy(window) or any(not isValid(c) or not c.isVisible() for c, _, _ in items):
        return
    if policy == 'select':
        CardSelection(window, direction, items)
    else:
        execute_transfer(window, direction, items, policy)
