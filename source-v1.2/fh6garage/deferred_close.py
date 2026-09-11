"""Drain active work before honoring a window close; never terminate workers."""
from PySide6.QtCore import QThread, QTimer


def closing(window):
    return bool(getattr(window, '_fh6_close_requested', False))


def active_work(window):
    if getattr(window, '_busy_depth', 0):
        return True
    if any(getattr(window, name, False) for name in (
        '_fh6_thumbnail_write_running', '_fh6_auto_backup_running',
        '_fh6_export_running', '_fh6_import_running', '_fh6_external_import_running',
        '_fh6_memory_scan_running', '_game_navigation_pending',
    )):
        return True
    controller = getattr(window, '_fh6_application_controller', None)
    if controller is not None and (controller.worker is not None or controller.observer_worker is not None):
        return True
    from .livery_2d_view import Livery2DController
    if any(item.worker is not None for item in window.findChildren(Livery2DController)):
        return True
    threads = list(window.findChildren(QThread))
    threads.extend(getattr(window, name, None) for name in ('_scan_thread', '_db_update_thread', '_fh6_memory_thread'))
    for thread in threads:
        try:
            if thread is not None and thread.isRunning():
                return True
        except RuntimeError:
            pass  # already destroyed by its completion handler
    return False


def prepare(window):
    if closing(window):
        return
    window._fh6_close_requested = True
    watcher = getattr(window, '_fh6_navigation_watch', None)
    if watcher is not None:
        watcher.clear()
    controller = getattr(window, '_fh6_application_controller', None)
    if controller is not None:
        controller.timer.stop()
        controller.pending_scan = None
    timer = getattr(window, '_fh6_completion_refresh_timer', None)
    if timer is not None:
        timer.stop()
    thumbnails = getattr(window, '_fh6_thumbnail_marks', None)
    if thumbnails is not None:
        thumbnails.timer.stop()
        thumbnails.pending = False
        thumbnails.pending_full = False
        thumbnails.pending_records.clear()
    # Keep the title-bar close button available, but prevent new user work.
    central = window.centralWidget()
    if central is not None:
        central.setEnabled(False)


def wait_for_close(window):
    prepare(window)
    message = '진행 중인 작업이 끝나면 자동으로 종료합니다.'
    window._show_status(message, 0)
    overlay = getattr(window, '_busy_overlay', None)
    if overlay is not None and overlay.isVisible():
        overlay.message.setText(message)
    timer = getattr(window, '_fh6_close_wait_timer', None)
    if timer is None:
        timer = QTimer(window)
        timer.setInterval(200)
        def attempt():
            if not active_work(window):
                timer.stop()
                window.close()
        timer.timeout.connect(attempt)
        window._fh6_close_wait_timer = timer
    timer.start()
