"""Settings, backup selection/deletion and optional automatic save watching."""
from datetime import datetime
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QStyle, QToolButton, QVBoxLayout, QWidget, QSizePolicy)

from .app_options import AppOptions, load_options, save_options, options_snapshot
from .backup_policies import record_locked
from .models import LiveryRecord
from .light_controls import LIGHT_CONTROLS_STYLE
from .deferred_close import closing


OPTION_GROUPS = (
    ('자동 처리', (
        ('auto_backup', '자동 백업'),
        ('auto_livery_detection', '자동 리버리 인식'),
    )),
    ('미리보기', (
        ('render_cache', '렌더링 캐시 저장 및 재사용'),
        ('skip_vehicle_materials', '3D 차량 재질 생략'),
    )),
    ('표시', (
        ('show_download_date', '다운로드 날짜 표시'),
        ('show_auction_badge', '경매장 표시'),
        ('show_hide_button', '숨김 버튼 활성화'),
        ('write_thumbnail_marks', '썸네일에 쓰기'),
    )),
    ('백업 및 보호', (
        ('disable_export_cut', '내보내기에서 잘라내기 비활성화'),
        ('backup_allow_different_name', '이름이 다른 리버리 중복 백업 허용'),
        ('backup_allow_duplicates', '이름이 같은 리버리 중복 백업 허용'),
        ('warn_applied_delete_move', '적용 중인 리버리를 삭제하기 위해 이동할 때 경고'),
    )),
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('설정')
        self.setStyleSheet(LIGHT_CONTROLS_STYLE)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(10)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self.resize(560, min(720, self.screen().availableGeometry().height() - 48))
        self.boxes = {}
        self.reapply_requested = False
        options = load_options()
        option_height = max(22, self.fontMetrics().height() + 4)
        for title, entries in OPTION_GROUPS:
            group = QGroupBox(title)
            group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            rows = QVBoxLayout(group)
            rows.setSpacing(6)
            for name, label in entries:
                box = QCheckBox(label)
                box.setObjectName(name)
                box.setFixedHeight(option_height)
                if name == 'write_thumbnail_marks':
                    box.setToolTip('연결된 썸네일 파일에 Auction·잠금 표시를 씁니다. 원본을 별도 보관하며 쓰기를 끄면 복원합니다.')
                box.setChecked(getattr(options, name))
                self.boxes[name] = box
                if name == 'write_thumbnail_marks':
                    row = QHBoxLayout()
                    row.addWidget(box)
                    row.addStretch(1)
                    self.reapply_button = QPushButton('재적용')
                    self.reapply_button.setFixedHeight(option_height)
                    self.reapply_button.setStyleSheet('padding: 2px 10px;')
                    self.reapply_button.setEnabled(box.isChecked())
                    self.reapply_button.setToolTip('설정을 저장하고 새로 연결된 썸네일에 다시 씁니다. 성공한 항목의 이전 원본 백업은 교체합니다.')
                    box.toggled.connect(self.reapply_button.setEnabled)
                    self.reapply_button.clicked.connect(self.reapply)
                    row.addWidget(self.reapply_button)
                    rows.addLayout(row)
                else:
                    rows.addWidget(box)
            body_layout.addWidget(group)
        workers = QFormLayout()
        self.workers = QSpinBox()
        self.workers.setObjectName('render_workers')
        self.workers.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.worker_down = QPushButton('-')
        self.worker_up = QPushButton('+')
        self.worker_down.setFixedWidth(36)
        self.worker_up.setFixedWidth(36)
        self.worker_down.setAccessibleName('동시 작업 수 줄이기')
        self.worker_up.setAccessibleName('동시 작업 수 늘리기')
        self.worker_down.setToolTip('동시 작업 수 줄이기 · 최솟값은 자동')
        self.worker_up.setToolTip('동시 작업 수 늘리기 · 자동 다음은 1')
        self.worker_down.clicked.connect(self.workers.stepDown)
        self.worker_up.clicked.connect(self.workers.stepUp)
        self.workers.setRange(0, os.cpu_count() or 1)
        self.workers.setSpecialValueText('자동')
        self.workers.setValue(options.render_workers)
        self.workers.setToolTip('텍스처 변환의 동시 작업 수입니다. 특정 CPU 코어를 고정하지 않습니다.')
        worker_row = QHBoxLayout()
        worker_row.addWidget(self.workers)
        worker_row.addWidget(self.worker_down)
        worker_row.addWidget(self.worker_up)
        def update_steps(value):
            self.worker_down.setEnabled(value > self.workers.minimum())
            self.worker_up.setEnabled(value < self.workers.maximum())
        self.workers.valueChanged.connect(update_steps)
        update_steps(self.workers.value())
        workers.addRow('렌더링 동시 작업 수', worker_row)
        body_layout.addLayout(workers)
        note = QLabel('미리보기 설정은 다음 작업부터 적용됩니다.\n캐시 사용을 꺼도 기존 파일을 삭제하지 않으며, 새 결과는 임시로 처리합니다.')
        note.setWordWrap(True)
        body_layout.addWidget(note)
        body_layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('저장')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        from .license_notices import show_licenses
        self.licenses_button = buttons.addButton('오픈소스 및 라이선스', QDialogButtonBox.ButtonRole.ActionRole)
        self.licenses_button.clicked.connect(lambda: show_licenses(self))
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @Slot()
    def reapply(self):
        self.reapply_requested = True
        self.save()

    @Slot()
    def save(self):
        values = {name: box.isChecked() for name, box in self.boxes.items()}
        options = AppOptions(**values, render_workers=self.workers.value())
        if not save_options(options):
            QMessageBox.warning(self, '설정', '설정을 저장하지 못했습니다.')
            return
        self.accept()


class ExportSelectionDialog(QDialog):
    def __init__(self, records, parent=None):
        super().__init__(parent)
        self.setWindowTitle('내보낼 리버리 선택')
        self.setStyleSheet(LIGHT_CONTROLS_STYLE)
        self.resize(600, 500)
        layout = QVBoxLayout(self)
        self.records = list(records)
        self.items = QListWidget()
        for record in self.records:
            item = QListWidgetItem(f'{record.header.name or "(이름 없음)"} · {record.header.creator or "-"} · {record.car_id}')
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.items.addItem(item)
        layout.addWidget(self.items)
        row = QHBoxLayout()
        for label, state in (('전체 선택', Qt.CheckState.Checked), ('선택 해제', Qt.CheckState.Unchecked)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, value=state: self.set_all(value))
            row.addWidget(button)
        layout.addLayout(row)
        self.count = QLabel()
        self.items.itemChanged.connect(self.update_count)
        layout.addWidget(self.count)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('선택 항목 내보내기')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.update_count()

    def selected_records(self):
        return [record for i, record in enumerate(self.records)
                if self.items.item(i).checkState() == Qt.CheckState.Checked]

    def set_all(self, state):
        self.items.blockSignals(True)
        for index in range(self.items.count()):
            self.items.item(index).setCheckState(state)
        self.items.blockSignals(False)
        self.update_count()

    def update_count(self, *_):
        count = len(self.selected_records())
        self.count.setText(f'{count}개 선택 / 전체 {len(self.records)}개')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(count > 0)


class _DatePositioner(QObject):
    def __init__(self, host, label, *, top=False):
        super().__init__(host)
        self.host, self.label = host, label
        self.top = top
        host.installEventFilter(self)
        self.position()

    def position(self):
        self.label.adjustSize()
        self.label.move(max(0, (self.host.width() - self.label.width()) // 2),
                        6 if self.top else max(0, self.host.height() - self.label.height() - 6))
        self.label.raise_()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.position()
        return False


def apply_card_options(card, record):
    options = load_options()
    card._fh6_option_record = record
    hide = getattr(card, '_fh6_hide_button', None)
    if hide is not None:
        hide.setVisible(True)
        hide.setEnabled(options.show_hide_button)
    badge = getattr(card, '_fh6_auction_badge', None)
    if badge is not None:
        badge.setText('Auction')
        badge.setStyleSheet('background:rgba(255,255,255,220); color:#555a68; border-radius:4px; padding:2px 5px; font-size:9pt;')
        if not hasattr(card, '_fh6_auction_positioner'):
            card._fh6_auction_positioner = _DatePositioner(badge.parentWidget(), badge, top=False)
        card._fh6_auction_positioner.position()
        badge.setVisible(options.show_auction_badge)
    image = getattr(card, '_fh6_image_label', None)
    label = getattr(card, '_fh6_download_date_label', None)
    if image is not None and label is None:
        host = image.parentWidget()
        label = QLabel(host)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setStyleSheet('background:rgba(255,255,255,220); color:#555a68; border-radius:4px; padding:2px 5px; font-size:9pt;')
        card._fh6_download_date_label = label
        card._fh6_date_positioner = _DatePositioner(host, label, top=True)
    if label is not None:
        value = getattr(record, 'downloaded_at', None)
        try:
            text = datetime.fromtimestamp(value).strftime('%Y-%m-%d') if value is not None else ''
        except (ValueError, OSError, OverflowError):
            text = ''
        label.setText('다운로드:' + text if text else '')
        label.setVisible(options.show_download_date and bool(text))
        card._fh6_date_positioner.position()


def _delete_card_backup(window, card):
    from . import v1_3_4_backup_export_patch as backup
    from .backup_delete import delete_backup
    record = card.property('backupRecord')
    if not isinstance(record, LiveryRecord) or record_locked(window, record) or card.property('fh6MoveLocked'):
        window._show_status('잠긴 백업은 삭제하지 않습니다.', 4000)
        return
    if any(getattr(window, attr, False) for attr in ('_fh6_export_running', '_fh6_import_running', '_fh6_auto_backup_running', '_fh6_external_import_running', '_fh6_backup_load_running', '_fh6_backup_relayout_active')):
        window._show_status('백업 작업이 끝난 뒤 다시 시도해 주세요.', 4000)
        return
    root = backup._backup_root(window)
    entry = getattr(card, '_fh6_backup_entry', {})
    if root is None or not backup._backup_path_is_safe(window, root) or not entry.get('relative_path'):
        return
    answer = QMessageBox.question(window, '백업 삭제',
        f'{record.header.name or record.container_name}\n\n선택한 백업을 삭제하시겠습니까? 게임 원본은 유지됩니다.',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
    if answer != QMessageBox.StandardButton.Yes:
        return
    from .backup_transaction import backup_busy
    if (backup_busy(window) or getattr(window, '_fh6_backup_load_running', False)
            or getattr(window, '_fh6_backup_relayout_active', False)
            or record_locked(window, record) or card.property('fh6MoveLocked')
            or backup._backup_root(window) != root):
        window._show_status('작업 상태 또는 잠금이 변경되어 삭제를 취소했습니다.', 4000)
        return
    from . import v1_3_4_backup_lazy_load_patch as lazy
    signature = lazy._repository_signature(root)
    cleanup_error = None
    try:
        delete_backup(root, entry['relative_path'])
    except Exception as exc:
        # Cleanup can fail after the index deletion has committed. Reflect only
        # confirmed removal; an index/rename failure keeps every card intact.
        from .backup_export import load_index
        try:
            removed = not any(e.get('relative_path') == entry['relative_path']
                              for e in load_index(root).get('entries', []))
        except Exception:
            removed = False
        if not removed:
            QMessageBox.warning(window, '백업 삭제 실패', str(exc))
            return
        cleanup_error = exc
    lazy._remove_deleted_backup(window, root, entry['relative_path'], signature)
    backup._refresh_main_export_states(window)
    if cleanup_error is not None:
        QMessageBox.warning(window, '백업 정리 일부 실패',
                            f'백업 목록에서는 삭제되었습니다. 남은 파일 정리에 실패했습니다.\n{cleanup_error}')


def configure_backup_delete(window, card, record):
    button = getattr(card, '_fh6_game_move_button', None)
    if button is None:
        button = QToolButton(card)
        card._fh6_game_move_button = button
        grid = getattr(card, '_fh6_action_grid', None)
        if grid is not None:
            grid.addWidget(button, 0, 0)
    try:
        button.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass
    button.setObjectName('fh6BackupDeleteButton')
    button.setIcon(window.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
    button.setToolTip('백업 삭제')
    button.setProperty('fh6UnlockedTooltip', '백업 삭제')
    button.setAccessibleName('백업 삭제')
    button.setEnabled(not record_locked(window, record) and not card.property('fh6MoveLocked'))
    button.show()
    button.clicked.connect(lambda _=False: _delete_card_backup(window, card))


class _AutoBackupWorker(QThread):
    result_ready = Signal(object)
    error = Signal(str)

    def __init__(self, root, records, parent):
        super().__init__(parent)
        self.root, self.records = root, list(records)

    def run(self):
        try:
            from .backup_export import content_sha256
            from .v1_3_4_backup_import_refinement_patch import _safe_export_records, _valid_backup_entries
            with options_snapshot():
                _, entries, _ = _valid_backup_entries(self.root)
                # Automatic polling must not produce identical backups forever,
                # even when manual duplicate backups are allowed.
                known = {(e.get('kind'), e.get('content_sha256'), e.get('name'), e.get('original_container_name')) for e in entries}
                pending = [r for r in self.records if (r.kind, content_sha256(r), r.header.name, r.container_name) not in known]
                self.result_ready.emit(_safe_export_records(self.root, pending))
        except Exception as exc:
            self.error.emit(str(exc))


class _ObservationWorker(QThread):
    result_ready = Signal(object)

    def __init__(self, observation, token, parent):
        super().__init__(parent)
        self.observation, self.token = observation, token

    def run(self):
        self.result_ready.emit((self.token, self.observation.check()))


class ApplicationController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.last_result = None
        self.signature = None
        self.worker = None
        self.auto_start_attempted = False
        self.observation = None
        self.observer_worker = None
        self.generation = 0
        timer = QTimer(self)
        timer.setInterval(3000)
        timer.timeout.connect(self.poll)
        timer.start()
        self.timer = timer

    @Slot()
    def settings(self):
        before = load_options()
        dialog = SettingsDialog(self.window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from PySide6.QtWidgets import QFrame
            for card in self.window.findChildren(QFrame):
                record = getattr(card, '_fh6_option_record', None)
                if record is not None:
                    apply_card_options(card, record)
                    from .thumbnail_marks_ui import update_card
                    update_card(self.window, card, record)
            for name in ('livery_table', 'tuning_table'):
                table = getattr(self.window, name, None)
                if table is not None:
                    table.setColumnHidden(7, not load_options().show_download_date)
            after = load_options()
            if before.auto_livery_detection != after.auto_livery_detection:
                self.last_result = None
                self.auto_start_attempted = False
                self.invalidate()
            if (dialog.reapply_requested or before.write_thumbnail_marks != after.write_thumbnail_marks
                    or (after.write_thumbnail_marks and before.show_auction_badge != after.show_auction_badge)):
                from .thumbnail_marks_ui import request
                request(self.window, reapply=dialog.reapply_requested)

    def invalidate(self, *_):
        self.generation += 1
        if self.observation is not None:
            self.observation.cancelled = True
        self.observation = None
        self.window._fh6_observed_liveries = None

    def main_scan_committed(self):
        if closing(self.window):
            return
        watcher = getattr(self.window, '_fh6_navigation_watch', None)
        if watcher is not None:
            watcher.scan_completed()
        from .thumbnail_marks_ui import request
        if load_options().write_thumbnail_marks:
            request(self.window)
        self.invalidate()
        from .refresh_history import LiveryRefreshDiff
        self.window._fh6_latest_livery_diff = LiveryRefreshDiff(False, '', [], [], [])
        from .v1_4_ui_completion_patch import _update_recent_change_banner
        _update_recent_change_banner(self.window)
        dialog = getattr(self.window, '_fh6_change_dialog', None)
        if dialog is not None and hasattr(dialog, '_fh6_update_changes'):
            dialog._fh6_update_changes()

    def observation_done(self, payload):
        token, value = payload
        if token != self.generation or not load_options().auto_livery_detection or value is None:
            return
        if self.window.result is not self.last_result or self.window.path_edit.text().strip() != self.observed_path:
            return
        if self.busy():
            self.observation.accepted = None
            return
        diff, records = value
        self.window._fh6_latest_livery_diff = diff
        self.window._fh6_observed_liveries = records
        from .v1_4_ui_completion_patch import _update_recent_change_banner
        _update_recent_change_banner(self.window)
        dialog = getattr(self.window, '_fh6_change_dialog', None)
        if dialog is not None and hasattr(dialog, '_fh6_update_changes'):
            dialog._fh6_update_changes()
        # Only navigation bookkeeping changes; main records/cards stay intact.
        from .game_navigation import GameGridSession, NavigationItem
        def navigation_key(record):
            matches = [r for r in self.last_result.liveries if r.kind == record.kind and
                       (r.container_name == record.container_name or
                        (r.header.guid and r.header.guid == record.header.guid) or
                        (r.content_sha256 and r.content_sha256 == record.content_sha256))]
            original = matches[0] if len(matches) == 1 else record
            return self.window._content_annotation_key('livery', original)

        self.window._game_navigation_sessions['livery'] = GameGridSession(
            NavigationItem(navigation_key(r), r.car_id,
                           '|'.join((r.container_name, r.header.guid or '', r.header.name or '')))
            for r in records if r.kind == 'Livery' and navigation_key(r) not in
            getattr(getattr(self.window, '_fh6_navigation_watch', None), 'removed', set()))

    def observation_finished(self):
        self.observer_worker.deleteLater()
        self.observer_worker = None
        if closing(self.window):
            self.pending_scan = None
            return
        pending = getattr(self, 'pending_scan', None)
        if pending is not None:
            self.pending_scan = None
            args, kwargs = pending
            requested = args[0] if args else kwargs.get('path')
            if requested is not None and Path(requested).resolve() == Path(self.window.path_edit.text().strip()).resolve():
                self.window.start_scan(*args, **kwargs)

    def busy(self):
        from PySide6.QtWidgets import QApplication
        window = self.window
        thread = getattr(window, '_scan_thread', None)
        return (QApplication.activeModalWidget() is not None
                or bool(getattr(window, '_busy_depth', 0))
                or any(getattr(window, flag, False) for flag in
                    ('_fh6_export_running', '_fh6_import_running', '_fh6_auto_backup_running',
                     '_fh6_external_import_running', '_game_navigation_pending'))
                or (thread is not None and thread.isRunning()))

    @Slot()
    def poll(self):
        if closing(self.window):
            return
        window = self.window
        if getattr(window, '_fh6_thumbnail_write_running', False):
            return
        options = load_options()
        if not options.auto_livery_detection and self.observation is not None:
            self.invalidate()
        from PySide6.QtWidgets import QApplication
        if QApplication.activeModalWidget() is not None or getattr(window, '_fh6_card_selection', None):
            return
        if getattr(window, '_busy_depth', 0) or any(getattr(window, flag, False) for flag in
                ('_fh6_export_running', '_fh6_import_running', '_fh6_auto_backup_running', '_fh6_external_import_running')):
            return
        thread = getattr(window, '_scan_thread', None)
        if thread is not None and thread.isRunning():
            return
        result = getattr(window, 'result', None)
        options = load_options()
        if result is None:
            raw = window.path_edit.text().strip()
            if options.auto_livery_detection and not self.auto_start_attempted and raw and Path(raw).is_dir():
                self.auto_start_attempted = True
                window.refresh_scan()
            return
        changed_result = result is not self.last_result
        if changed_result:
            self.last_result = result
            self.signature = None
            if options.auto_backup:
                self.start_backup(result.liveries)
        if not options.auto_livery_detection:
            return
        if self.observer_worker is not None or self.busy():
            return
        selected = getattr(result.metadata, 'selected_path', None)
        if selected is not None and Path(window.path_edit.text().strip()).resolve() != Path(selected).resolve():
            return
        if self.observation is None or changed_result:
            self.invalidate()
            from .livery_watch import Observation
            self.observation = Observation(result.metadata.containers_root, result.liveries, getattr(window, 'car_db', None))
            self.observed_path = window.path_edit.text().strip()
        if window.path_edit.text().strip() != self.observed_path:
            self.invalidate()
            return
        worker = _ObservationWorker(self.observation, self.generation, self)
        worker.result_ready.connect(self.observation_done)
        worker.finished.connect(self.observation_finished)
        self.observer_worker = worker
        worker.start()

    def start_backup(self, records):
        if closing(self.window):
            return
        from . import v1_3_4_backup_export_patch as backup
        root = backup._backup_root(self.window)
        if root is None or not backup._backup_path_is_safe(self.window, root):
            return
        self.window._fh6_auto_backup_running = True
        worker = _AutoBackupWorker(root, records, self.window)
        worker.result_ready.connect(self.backup_done)
        worker.error.connect(self.backup_error)
        worker.finished.connect(self.backup_finished)
        self.worker = worker
        worker.start()

    @Slot(object)
    def backup_done(self, summary):
        from . import v1_3_4_backup_export_patch as backup
        self.window._fh6_backup_presence_cache = ('', set(), set())
        backup._refresh_main_export_states(self.window)
        if summary.exported or summary.failed:
            self.window._show_status(f'자동 백업: 저장 {len(summary.exported)}개 · 실패 {len(summary.failed)}개', 5000)
            backup._rebuild_backup_cards(self.window)

    @Slot(str)
    def backup_error(self, message):
        self.window._show_status('자동 백업 실패: ' + message, 6000)

    @Slot()
    def backup_finished(self):
        self.window._fh6_auto_backup_running = False
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None


def install_application_controls(MainWindow):
    if getattr(MainWindow, '_fh6_application_controls', False):
        return
    from . import v1_3_4_backup_export_patch as backup
    from . import v1_3_4_backup_import_refinement_patch as refinement
    from . import v1_3_4_backup_toolbar_followup_patch as toolbar
    original_init = MainWindow.__init__
    original_card = MainWindow._make_saved_content_card
    original_backup = refinement._configure_backup_card
    original_close = MainWindow.closeEvent
    original_start_scan = MainWindow.start_scan

    def start_scan(self, *args, **kwargs):
        if closing(self):
            return
        watcher = getattr(self, '_fh6_navigation_watch', None)
        if watcher is not None and not watcher.refresh_requested:
            watcher.clear()
        if getattr(self, '_fh6_thumbnail_write_running', False):
            raw = self.path_edit.text()
            QTimer.singleShot(200, lambda: self.start_scan(*args, **kwargs) if self.path_edit.text() == raw else None)
            return
        controller = getattr(self, '_fh6_application_controller', None)
        if controller is not None:
            controller.invalidate()
            if controller.observer_worker is not None:
                controller.pending_scan = (args, kwargs)
                return
        return original_start_scan(self, *args, **kwargs)

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        controller = ApplicationController(self)
        self._fh6_application_controller = controller
        from .thumbnail_marks_ui import Controller
        self._fh6_thumbnail_marks = Controller(self)
        self.path_edit.textChanged.connect(controller.invalidate)
        button = QPushButton('설정')
        button.setObjectName('nav')
        button.setAccessibleName('설정')
        self._fh6_settings_button = button
        button.clicked.connect(controller.settings)
        side = self.language_combo.parentWidget().layout()
        performance = getattr(self, 'performance_nav_button', None)
        index = side.indexOf(performance) if performance is not None else -1
        side.insertWidget(index + 1 if index >= 0 else max(0, side.indexOf(self.language_label)), button)
        self.livery_export_visible_button.setText('내보내기')
        self.backup_export_button.setText('내보내기')
        self.backup_export_button.setToolTip('현재 백업 목록을 리버리로 내보내기')
        for name in ('livery_table', 'tuning_table'):
            table = getattr(self, name, None)
            if table is not None:
                table.setColumnHidden(7, not load_options().show_download_date)

    def card(self, content_type, record, key):
        result = original_card(self, content_type, record, key)
        apply_card_options(result, record)
        from .thumbnail_marks_ui import update_card
        update_card(self, result, record)
        return result

    def backup_card(window, card, record, *args, **kwargs):
        original_backup(window, card, record, *args, **kwargs)
        paths = getattr(window, '_fh6_backup_lock_paths', set())
        paths.add(str(record.container_path.resolve()).casefold())
        window._fh6_backup_lock_paths = paths
        configure_backup_delete(window, card, record)
        from .v1_3_4_card_features_patch import _install_livery_lock
        _install_livery_lock(window, card, 'backup-path::' + str(record.container_path.resolve()).casefold())
        lock = getattr(card, '_fh6_lock_placeholder_button', None)
        if lock is not None:
            lock.setEnabled(True)
            lock.show()
        apply_card_options(card, record)
        from .thumbnail_marks_ui import update_card
        update_card(window, card, record)

    def export_selected(window):
        from .card_transfer import request_transfer
        request_transfer(window, 'game')

    def export_backup_selected(window):
        from .card_transfer import request_transfer
        request_transfer(window, 'backup')

    def close(self, event):
        from .deferred_close import active_work, prepare, wait_for_close
        if active_work(self):
            event.ignore()
            wait_for_close(self)
            return
        prepare(self)
        original_close(self, event)

    MainWindow.__init__ = init
    MainWindow._make_saved_content_card = card
    MainWindow.closeEvent = close
    MainWindow.start_scan = start_scan
    refinement._configure_backup_card = backup_card
    backup._export_visible = export_selected
    toolbar._export_game_only = export_backup_selected
    MainWindow._fh6_application_controls = True
