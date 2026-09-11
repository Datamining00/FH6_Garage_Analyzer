"""One-shot refresh after an explicitly requested scan or database update."""
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from .deferred_close import closing


def _busy(window):
    if QApplication.activeModalWidget() is not None:
        return True
    if getattr(window, '_busy_depth', 0) or getattr(window, '_fh6_card_selection', None):
        return True
    if any(getattr(window, flag, False) for flag in (
        '_fh6_export_running', '_fh6_import_running', '_fh6_auto_backup_running',
        '_fh6_external_import_running', '_game_navigation_pending', '_fh6_memory_scan_running', '_fh6_thumbnail_write_running')):
        return True
    for name in ('_scan_thread', '_db_update_thread', '_fh6_memory_thread'):
        thread = getattr(window, name, None)
        if thread is not None and thread.isRunning():
            return True
    return False


def request_refresh(window):
    """Coalesce completion events; wait for work/selection and reject stale paths."""
    if closing(window):
        return
    raw = window.path_edit.text().strip()
    if not raw or not Path(raw).is_dir():
        return
    timer = getattr(window, '_fh6_completion_refresh_timer', None)
    window._fh6_completion_refresh_path = raw
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        window._fh6_completion_refresh_timer = timer

        def attempt():
            if closing(window):
                return
            target = window._fh6_completion_refresh_path
            if window.path_edit.text().strip() != target or not Path(target).is_dir():
                return
            if _busy(window):
                timer.start(200)
                return
            window.refresh_scan()

        timer.timeout.connect(attempt)
    timer.start(0)
