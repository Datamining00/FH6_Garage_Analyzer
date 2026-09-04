from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, Slot

from . import performance_metrics as _metrics
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_lazy_load_patch as _lazy


class _BackupLoadGuiBridge(QObject):
    """Receive backup worker signals on the MainWindow/GUI thread."""

    def __init__(self, window: Any, token: _lazy._CancelToken) -> None:
        super().__init__(window)
        self._window = window
        self._token = token

    def _is_current(self) -> bool:
        return self._token is getattr(self._window, "_fh6_backup_cancel_token", None)

    def _record_handoff(self, signal_name: str) -> None:
        on_gui_thread = QThread.currentThread() is self._window.thread()
        _metrics.record(
            "backup.lazy.gui_handoff",
            0.0,
            detail=f"signal={signal_name} gui_thread={int(on_gui_thread)}",
        )

    @Slot(object)
    def worker_finished(self, result: object) -> None:
        self._record_handoff("finished")
        if self._is_current():
            _lazy._worker_finished(self._window, result, self._token)

    @Slot()
    def worker_cancelled(self) -> None:
        self._record_handoff("cancelled")
        if self._is_current():
            _lazy._worker_cancelled(self._window, self._token)

    @Slot(str)
    def worker_failed(self, message: str) -> None:
        self._record_handoff("failed")
        if self._is_current():
            _lazy._worker_failed(self._window, message, self._token)

    @Slot()
    def thread_finished(self) -> None:
        # The repository worker thread may finish before card chunks finish on
        # the GUI thread. Clear only worker/thread references here; keep this
        # bridge parented to the window until the next load replaces it.
        if self is getattr(self._window, "_fh6_backup_load_bridge", None):
            _lazy._clear_load_thread(self._window)


def _safe_start_full_load(
    window: Any,
    *,
    force: bool = False,
    message: str | None = None,
) -> None:
    if getattr(window, "_fh6_backup_load_running", False):
        return
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
    bridge = _BackupLoadGuiBridge(window, token)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.finished.connect(bridge.worker_finished)
    worker.cancelled.connect(bridge.worker_cancelled)
    worker.failed.connect(bridge.worker_failed)

    # Standard worker-thread shutdown path. UI callbacks above are delivered to
    # bridge slots because the bridge retains MainWindow/GUI thread affinity.
    worker.finished.connect(thread.quit)
    worker.cancelled.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(bridge.thread_finished)
    thread.finished.connect(thread.deleteLater)

    window._fh6_backup_load_thread = thread
    window._fh6_backup_load_worker = worker
    window._fh6_backup_load_bridge = bridge
    thread.start()


def apply_v1_3_4_backup_lazy_thread_bridge_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_lazy_thread_bridge_patched", False):
        return

    # Lazy-load callers resolve this module global at execution time, so replacing
    # it here covers first-tab load, explicit refresh, external dirty refresh and
    # older rebuild compatibility requests without touching the validated card
    # chunk implementation from Actions #110.
    _lazy._start_full_load = _safe_start_full_load
    MainWindow._fh6_v134_backup_lazy_thread_bridge_patched = True
