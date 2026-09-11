"""Settings, backup selection/deletion and optional automatic save watching."""
from datetime import datetime
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QStyle, QToolButton, QVBoxLayout, QWidget)

from .app_options import AppOptions, load_options, save_options, options_snapshot
from .backup_policies import record_locked
from .models import LiveryRecord


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
        ('show_download_date', '다운 날짜 표시'),
        ('show_auction_badge', '경매장 썸네일에 옥션 표시'),
        ('show_hide_button', '숨김 버튼 표시'),
    )),
    ('백업 및 보호', (
        ('disable_export_cut', '내보내기에서 잘라내기 비활성화'),
        ('backup_allow_different_name', '같은 리버리라도 이름이 다르면 백업 허용'),
        ('backup_allow_duplicates', '이름까지 같은 리버리도 중복 백업 허용'),
        ('warn_applied_delete_move', '적용 중인 리버리를 삭제하기 위해 이동할 때 경고'),
    )),
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('설정')
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self.resize(560, 650)
        self.boxes = {}
        options = load_options()
        for title, entries in OPTION_GROUPS:
            group = QGroupBox(title)
            rows = QVBoxLayout(group)
            for name, label in entries:
                box = QCheckBox(label)
                box.setObjectName(name)
                box.setChecked(getattr(options, name))
                self.boxes[name] = box
                rows.addWidget(box)
            body_layout.addWidget(group)
        workers = QFormLayout()
        self.workers = QSpinBox()
        self.workers.setObjectName('render_workers')
        self.workers.setRange(0, os.cpu_count() or 1)
        self.workers.setSpecialValueText('자동')
        self.workers.setValue(options.render_workers)
        self.workers.setToolTip('텍스처 변환의 동시 작업 수입니다. 특정 CPU 코어를 고정하지 않습니다.')
        workers.addRow('렌더링 CPU 작업 수', self.workers)
        body_layout.addLayout(workers)
        note = QLabel('미리보기 설정은 다음 작업부터 적용됩니다.\n캐시 OFF는 기존 파일을 삭제하지 않으며, 새 결과는 임시로 처리합니다.')
        note.setWordWrap(True)
        body_layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('저장')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
    def __init__(self, host, label):
        super().__init__(host)
        self.host, self.label = host, label
        host.installEventFilter(self)
        self.position()

    def position(self):
        self.label.adjustSize()
        self.label.move(max(0, (self.host.width() - self.label.width()) // 2),
                        max(0, self.host.height() - self.label.height() - 6))
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
        hide.setVisible(options.show_hide_button)
    badge = getattr(card, '_fh6_auction_badge', None)
    if badge is not None:
        badge.setText('옥션')
        badge.setVisible(options.show_auction_badge)
    image = getattr(card, '_fh6_image_label', None)
    label = getattr(card, '_fh6_download_date_label', None)
    if image is not None and label is None:
        host = image.parentWidget()
        label = QLabel(host)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setStyleSheet('background:rgba(255,255,255,220); color:#555a68; border-radius:4px; padding:2px 5px; font-size:9pt;')
        card._fh6_download_date_label = label
        card._fh6_date_positioner = _DatePositioner(host, label)
    if label is not None:
        value = getattr(record, 'downloaded_at', None)
        try:
            text = datetime.fromtimestamp(value).strftime('%Y-%m-%d') if value is not None else ''
        except (ValueError, OSError, OverflowError):
            text = ''
        label.setText('다운 ' + text if text else '')
        label.setVisible(options.show_download_date and bool(text))
        card._fh6_date_positioner.position()


def _delete_card_backup(window, card):
    from . import v1_3_4_backup_export_patch as backup
    from .backup_delete import delete_backup
    record = card.property('backupRecord')
    if not isinstance(record, LiveryRecord) or record_locked(window, record) or card.property('fh6MoveLocked'):
        window._show_status('잠긴 백업은 삭제하지 않습니다.', 4000)
        return
    if any(getattr(window, attr, False) for attr in ('_fh6_export_running', '_fh6_import_running', '_fh6_auto_backup_running')):
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
    try:
        delete_backup(root, entry['relative_path'])
    except Exception as exc:
        QMessageBox.warning(window, '백업 삭제 실패', str(exc))
    window._fh6_backup_presence_cache = ('', set(), set())
    backup._rebuild_backup_cards(window)
    backup._refresh_main_export_states(window)


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


class ApplicationController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.last_result = None
        self.signature = None
        self.worker = None
        timer = QTimer(self)
        timer.setInterval(3000)
        timer.timeout.connect(self.poll)
        timer.start()
        self.timer = timer

    @Slot()
    def settings(self):
        if SettingsDialog(self.window).exec() == QDialog.DialogCode.Accepted:
            from PySide6.QtWidgets import QFrame
            for card in self.window.findChildren(QFrame):
                record = getattr(card, '_fh6_option_record', None)
                if record is not None:
                    apply_card_options(card, record)
            for name in ('livery_table', 'tuning_table'):
                table = getattr(self.window, name, None)
                if table is not None:
                    table.setColumnHidden(7, not load_options().show_download_date)
            self.last_result = None

    @Slot()
    def poll(self):
        window = self.window
        if getattr(window, '_busy_depth', 0) or any(getattr(window, flag, False) for flag in
                ('_fh6_export_running', '_fh6_import_running', '_fh6_auto_backup_running')):
            return
        thread = getattr(window, '_scan_thread', None)
        if thread is not None and thread.isRunning():
            return
        result = getattr(window, 'result', None)
        if result is None:
            return
        options = load_options()
        changed_result = result is not self.last_result
        if changed_result:
            self.last_result = result
            self.signature = None
            if options.auto_backup:
                self.start_backup(result.liveries)
        if not options.auto_livery_detection:
            return
        try:
            root = result.metadata.containers_root
            values = []
            for entry in os.scandir(root):
                if entry.name.startswith(('Livery_', 'SoulBoundLivery_')) and entry.is_dir(follow_symlinks=False):
                    payload = Path(entry.path) / 'C_livery'
                    stat = payload.stat() if payload.is_file() else entry.stat()
                    values.append((entry.name, stat.st_size, stat.st_mtime_ns))
            signature = tuple(sorted(values))
        except OSError:
            return
        if self.signature is not None and signature != self.signature:
            window.refresh_scan()
        self.signature = signature

    def start_backup(self, records):
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

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        controller = ApplicationController(self)
        self._fh6_application_controller = controller
        button = QPushButton('설정')
        button.setObjectName('fh6SettingsButton')
        button.clicked.connect(controller.settings)
        side = self.language_combo.parentWidget().layout()
        side.insertWidget(max(0, side.indexOf(self.language_label)), button)
        self.livery_export_visible_button.setText('선택 내보내기')
        self.backup_export_button.setText('선택 내보내기')
        self.backup_export_button.setToolTip('게임 리버리를 선택해서 백업으로 내보내기')
        for name in ('livery_table', 'tuning_table'):
            table = getattr(self, name, None)
            if table is not None:
                table.setColumnHidden(7, not load_options().show_download_date)

    def card(self, content_type, record, key):
        result = original_card(self, content_type, record, key)
        apply_card_options(result, record)
        return result

    def backup_card(window, card, record, *args, **kwargs):
        original_backup(window, card, record, *args, **kwargs)
        configure_backup_delete(window, card, record)
        apply_card_options(card, record)

    def export_selected(window):
        records = backup._visible_game_liveries(window)
        dialog = ExportSelectionDialog(records, window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            backup._request_export(window, dialog.selected_records())

    def export_backup_selected(window):
        # Include already backed-up records so the duplicate options are usable.
        kind = toolbar._selected_source_kind(window)
        needle = window.backup_search.text().strip().casefold()
        records = [r for r in getattr(getattr(window, 'result', None), 'liveries', [])
                   if r.kind == kind and (not needle or needle in
                       f'{r.header.name} {r.header.creator} {window._car_label(r.car_id)} {r.car_id}'.casefold())]
        dialog = ExportSelectionDialog(records, window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            backup._request_export(window, dialog.selected_records())

    def close(self, event):
        from .livery_2d_view import Livery2DController
        if any(controller.worker is not None for controller in self.findChildren(Livery2DController)):
            event.ignore()
            self._show_status('2D 렌더링을 마친 뒤 종료할 수 있습니다.', 4000)
            return
        if getattr(self, '_fh6_auto_backup_running', False):
            event.ignore()
            self._show_status('자동 백업을 마친 뒤 종료할 수 있습니다.', 4000)
            return
        original_close(self, event)

    MainWindow.__init__ = init
    MainWindow._make_saved_content_card = card
    MainWindow.closeEvent = close
    refinement._configure_backup_card = backup_card
    backup._export_visible = export_selected
    toolbar._export_game_only = export_backup_selected
    MainWindow._fh6_application_controls = True
