from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QSize, QThread, Signal, Slot
from PySide6.QtWidgets import QPushButton, QToolButton

from . import v1_3_4_backup_export_patch as _backup_ui
from .backup_export import BackupRepositoryError, LiveryRecord, backup_contains_record
from .card_icons import icon as card_icon


class _ExportUiBridge(QObject):
    """Queue every export completion callback onto the MainWindow GUI thread."""

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window

    @Slot(object)
    def finished(self, result: object) -> None:
        _backup_ui._export_finished(self.window, result)

    @Slot(str)
    def failed(self, message: str) -> None:
        _backup_ui._export_failed(self.window, message)

    @Slot()
    def thread_finished(self) -> None:
        _backup_ui._clear_export_thread(self.window)


def _set_export_state(window: Any, card: Any, record: LiveryRecord) -> None:
    button = getattr(card, "_fh6_export_placeholder_button", None)
    if not isinstance(button, QToolButton):
        return
    root = _backup_ui._backup_root(window)
    exported = False
    if root is not None:
        try:
            # Normal Livery records already carry a scanner hash. SoulBound
            # hashes are calculated only after a backup repository is configured
            # and then cached on the record for later checks in this process.
            exported = backup_contains_record(root, record, hash_if_needed=True)
        except BackupRepositoryError:
            exported = False
    button.setEnabled(True)
    button.setIcon(
        card_icon(
            "export",
            _backup_ui._ACTIVE_COLOR if exported else _backup_ui._INACTIVE_COLOR,
            20,
        )
    )
    button.setIconSize(QSize(20, 20))
    button.setStyleSheet(_backup_ui._action_style(exported))
    button.setProperty("fh6Exported", exported)
    button.setToolTip(
        _backup_ui._txt("이미 백업됨 · 다시 확인/내보내기", "Already backed up · verify/export again")
        if exported
        else _backup_ui._txt("이 리버리 내보내기", "Export this livery")
    )
    if not bool(button.property("fh6ExportActionInstalled")):
        button.setProperty("fh6ExportActionInstalled", True)
        button.clicked.connect(
            lambda _checked=False, owner=window, item=record: _backup_ui._request_export(owner, [item])
        )


def _request_export(window: Any, records: list[LiveryRecord]) -> None:
    if getattr(window, "_fh6_export_running", False) or not records:
        return
    root = _backup_ui._ensure_backup_root(window)
    if root is None:
        return
    if not _backup_ui._confirm_keep_source(window, len(records), operation="export"):
        return

    window._fh6_export_running = True
    bulk = getattr(window, "livery_export_visible_button", None)
    choose = getattr(window, "backup_choose_button", None)
    if isinstance(bulk, QPushButton):
        bulk.setEnabled(False)
    if isinstance(choose, QPushButton):
        choose.setEnabled(False)
    window._begin_busy(_backup_ui._txt("내보내는 중", "Exporting"))

    thread = QThread(window)
    worker = _backup_ui._ExportWorker(root, list(records))
    bridge = _ExportUiBridge(window)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(bridge.finished)
    worker.failed.connect(bridge.failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(bridge.thread_finished)
    thread.finished.connect(thread.deleteLater)
    window._fh6_export_thread = thread
    window._fh6_export_worker = worker
    window._fh6_export_bridge = bridge
    thread.start()


def apply_v1_3_4_backup_export_thread_fix_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_export_thread_fixed", False):
        return
    _backup_ui._set_export_state = _set_export_state
    _backup_ui._request_export = _request_export
    MainWindow._fh6_v134_backup_export_thread_fixed = True
