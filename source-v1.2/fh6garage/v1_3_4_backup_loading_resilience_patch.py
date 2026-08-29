from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Slot

from . import performance_metrics as _metrics
from . import v1_3_2_responsiveness_sort_patch as _responsive
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_lazy_load_patch as _lazy
from . import v1_3_4_backup_lazy_thread_bridge_patch as _bridge
from . import v1_3_4_backup_lazy_watch_patch as _watch


_PREVIOUS_THREAD_RETRY_MS = 25
_BACKUP_CARD_BUILD_CHUNK = 1
_BUSY_YIELD_INTERVAL_SECONDS = 0.033
_BUSY_PROCESS_EVENTS_MS = 5


class _StableBackupLoadGuiBridge(_bridge._BackupLoadGuiBridge):
    """Terminate the repository thread only after GUI delivery has begun."""

    def __init__(self, window: Any, token: _lazy._CancelToken, thread: QThread) -> None:
        super().__init__(window, token)
        self._thread = thread
        self._quit_requested = False

    def _request_thread_quit(self, signal_name: str) -> None:
        if self._quit_requested:
            return
        self._quit_requested = True
        _metrics.record(
            "backup.lazy.thread_lifecycle",
            0.0,
            detail=f"signal={signal_name} gui_received=1 quit_requested=1",
        )
        if self._thread.isRunning():
            self._thread.quit()

    @Slot(object)
    def worker_finished(self, result: object) -> None:
        self._request_thread_quit("finished")
        super().worker_finished(result)

    @Slot()
    def worker_cancelled(self) -> None:
        self._request_thread_quit("cancelled")
        super().worker_cancelled()

    @Slot(str)
    def worker_failed(self, message: str) -> None:
        self._request_thread_quit("failed")
        super().worker_failed(message)


def _schedule_retry(
    window: Any,
    *,
    force: bool,
    message: str | None,
) -> None:
    if getattr(window, "_fh6_backup_start_retry_pending", False):
        return
    window._fh6_backup_start_retry_pending = True

    def retry() -> None:
        window._fh6_backup_start_retry_pending = False
        _stable_start_full_load(window, force=force, message=message)

    QTimer.singleShot(_PREVIOUS_THREAD_RETRY_MS, retry)


def _stable_start_full_load(
    window: Any,
    *,
    force: bool = False,
    message: str | None = None,
) -> None:
    if getattr(window, "_fh6_backup_load_running", False):
        return

    # Card construction can finish after the repository worker has emitted its
    # terminal signal. Never start a second repository QThread until the prior
    # thread has actually stopped and its deferred cleanup has had a GUI turn.
    previous = getattr(window, "_fh6_backup_load_thread", None)
    if isinstance(previous, QThread) and previous.isRunning():
        _schedule_retry(window, force=force, message=message)
        return

    # The watcher layer wrapped _start_full_load before the thread bridge later
    # replaced that module global. Restore those pre-load responsibilities here.
    _watch._capture_scroll(window)
    _watch._configure_watcher(window)

    if (
        not force
        and getattr(window, "_fh6_backup_lazy_loaded", False)
        and not getattr(window, "_fh6_backup_cache_dirty", True)
    ):
        _metrics.record(
            "backup.lazy.cache_hit",
            0.0,
            item_count=len(getattr(window, "_fh6_backup_cards", []) or []),
        )
        _backup_ui._relayout_backup(window)
        return

    root = _backup_ui._backup_root(window)
    game = list(_backup_ui._game_records(window))
    token = _lazy._CancelToken()
    window._fh6_backup_load_running = True
    window._fh6_backup_cancel_token = token
    _lazy._set_controls_enabled(window, False)
    _lazy._show_delayed_loading_dialog(
        window,
        token,
        message
        or _backup_ui._txt(
            "백업 목록을 불러오는 중...",
            "Loading backup list...",
        ),
    )

    old_bridge = getattr(window, "_fh6_backup_load_bridge", None)
    if isinstance(old_bridge, QObject):
        old_bridge.deleteLater()

    thread = QThread(window)
    worker = _lazy._BackupLoadWorker(root, game, token)
    bridge = _StableBackupLoadGuiBridge(window, token, thread)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.finished.connect(bridge.worker_finished)
    worker.cancelled.connect(bridge.worker_cancelled)
    worker.failed.connect(bridge.worker_failed)

    # Do not connect worker terminal signals directly to thread.quit(). The
    # queued GUI bridge must receive the terminal result first. deleteLater is
    # posted to the worker thread while its event loop is still alive.
    worker.finished.connect(worker.deleteLater)
    worker.cancelled.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(bridge.thread_finished)
    thread.finished.connect(thread.deleteLater)

    window._fh6_backup_load_thread = thread
    window._fh6_backup_load_worker = worker
    window._fh6_backup_load_bridge = bridge
    thread.start()


def apply_v1_3_4_backup_loading_resilience_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_loading_resilience_patched", False):
        return

    # Give the Qt event loop a turn between every newly configured backup card.
    # This avoids a 12-card GUI burst freezing indeterminate progress animation.
    _lazy._CARD_BUILD_CHUNK = _BACKUP_CARD_BUILD_CHUNK

    # Existing livery/tuning busy loops already call _yield_busy_events(). Tighten
    # their visual cadence without adding per-card processEvents calls.
    _responsive._BUSY_YIELD_INTERVAL_SECONDS = _BUSY_YIELD_INTERVAL_SECONDS
    _responsive._BUSY_PROCESS_EVENTS_MS = _BUSY_PROCESS_EVENTS_MS

    _lazy._start_full_load = _stable_start_full_load
    _bridge._safe_start_full_load = _stable_start_full_load
    MainWindow._fh6_v134_backup_loading_resilience_patched = True
