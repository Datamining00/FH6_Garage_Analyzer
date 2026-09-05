from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QMetaObject, QObject, QThread, QTimer, Qt, Slot

from . import performance_metrics as _metrics
from . import v1_3_2_responsiveness_sort_patch as _responsive
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_lazy_load_patch as _lazy
from . import v1_3_4_backup_lazy_thread_bridge_patch as _bridge
from . import v1_3_4_backup_lazy_watch_patch as _watch
from .v1_3_ui_patch import GRID_MAX_COLUMNS


_PREVIOUS_THREAD_RETRY_MS = 25
_BACKUP_CARD_BUILD_CHUNK = 1
_BACKUP_RELAYOUT_CHUNK = 8
_BUSY_YIELD_INTERVAL_SECONDS = 0.033
_BUSY_PROCESS_EVENTS_MS = 5

_ORIGINAL_SYNC_BACKUP_WIDTHS = _backup_ui._sync_backup_widths
_ORIGINAL_REFRESH_BACKUP_THUMBNAILS = _backup_ui._refresh_backup_thumbnails
_ORIGINAL_LAZY_LOAD_FINISHED = _lazy._load_finished


class _StableBackupLoadGuiBridge(_bridge._BackupLoadGuiBridge):
    """Marshal every repository result through the bridge QObject event queue."""

    def __init__(self, window: Any, token: _lazy._CancelToken, thread: QThread) -> None:
        super().__init__(window, token)
        self._thread = thread
        self._quit_requested = False
        self._pending_result: object | None = None
        self._pending_failure = ""

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

    # These enqueue methods are intentionally safe to execute in the worker
    # thread. They never touch QWidget/QTimer state. QMetaObject.invokeMethod
    # performs the actual cross-thread hop using this QObject's thread affinity.
    def enqueue_finished(self, result: object) -> None:
        self._pending_result = result
        QMetaObject.invokeMethod(
            self,
            "_deliver_finished",
            Qt.ConnectionType.QueuedConnection,
        )

    def enqueue_cancelled(self) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_cancelled",
            Qt.ConnectionType.QueuedConnection,
        )

    def enqueue_failed(self, message: str) -> None:
        self._pending_failure = str(message)
        QMetaObject.invokeMethod(
            self,
            "_deliver_failed",
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot()
    def _deliver_finished(self) -> None:
        result = self._pending_result
        self._pending_result = None
        self._request_thread_quit("finished")
        _bridge._BackupLoadGuiBridge.worker_finished(self, result)

    @Slot()
    def _deliver_cancelled(self) -> None:
        self._request_thread_quit("cancelled")
        _bridge._BackupLoadGuiBridge.worker_cancelled(self)

    @Slot()
    def _deliver_failed(self) -> None:
        message = self._pending_failure
        self._pending_failure = ""
        self._request_thread_quit("failed")
        _bridge._BackupLoadGuiBridge.worker_failed(self, message)


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

    previous = getattr(window, "_fh6_backup_load_thread", None)
    if isinstance(previous, QThread) and previous.isRunning():
        _schedule_retry(window, force=force, message=message)
        return

    # Restore the watcher responsibilities that were bypassed when the earlier
    # bridge replaced the watcher-wrapped _start_full_load module global.
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
    # PySide6 can execute a Python slot in the emitter thread even when a
    # receiver QObject has GUI affinity. Keep these callbacks UI-free and use
    # QMetaObject.invokeMethod inside the bridge for the guaranteed queued hop.
    worker.finished.connect(bridge.enqueue_finished)
    worker.cancelled.connect(bridge.enqueue_cancelled)
    worker.failed.connect(bridge.enqueue_failed)

    # The worker thread is kept alive until the GUI-side delivery slot requests
    # quit. This removes a race between a terminal worker signal and UI handling.
    worker.finished.connect(worker.deleteLater)
    worker.cancelled.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(bridge.thread_finished)
    thread.finished.connect(thread.deleteLater)

    window._fh6_backup_load_thread = thread
    window._fh6_backup_load_worker = worker
    window._fh6_backup_load_bridge = bridge
    thread.start()


def _backup_card_width(window: Any, columns: int) -> int | None:
    scroll = getattr(window, "backup_grid_scroll", None)
    layout = getattr(window, "backup_grid_layout", None)
    if scroll is None or layout is None:
        return None
    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return None
    margins = layout.contentsMargins()
    gap = max(0, layout.horizontalSpacing())
    available = viewport.width() - margins.left() - margins.right() - gap * (columns - 1) - 4
    return max(1, available // columns)


def _stop_relayout_timer(window: Any) -> None:
    timer = getattr(window, "_fh6_backup_relayout_timer", None)
    if isinstance(timer, QTimer):
        timer.stop()
        timer.deleteLater()
    window._fh6_backup_relayout_timer = None


def _stable_sync_backup_widths(window: Any) -> None:
    # The async relayout applies width to each visible card in the same chunk in
    # which it is inserted. Skip the legacy O(N) second pass while it is active.
    if bool(getattr(window, "_fh6_backup_relayout_active", False)):
        return
    _ORIGINAL_SYNC_BACKUP_WIDTHS(window)


def _stable_refresh_backup_thumbnails(window: Any) -> None:
    if bool(getattr(window, "_fh6_backup_relayout_active", False)):
        window._fh6_backup_thumbnail_refresh_pending = True
        return
    _ORIGINAL_REFRESH_BACKUP_THUMBNAILS(window)


def _deferred_load_finished(window: Any) -> None:
    # _build_cards_from_result() calls _load_finished immediately after
    # _commit_cards(). Keep the loading dialog/controls in their loading state
    # until the last relayout chunk has actually reached the GUI.
    if bool(getattr(window, "_fh6_backup_relayout_active", False)):
        window._fh6_backup_finish_after_relayout = True
        return
    _ORIGINAL_LAZY_LOAD_FINISHED(window)


def _finish_relayout(window: Any, generation: int, started_ns: int, visible_cards: int) -> None:
    if generation != int(getattr(window, "_fh6_backup_relayout_generation", 0) or 0):
        return
    _stop_relayout_timer(window)
    layout = getattr(window, "backup_grid_layout", None)
    if layout is not None:
        try:
            layout.activate()
        except RuntimeError:
            pass
    host = getattr(window, "backup_grid_host", None)
    if host is not None:
        try:
            host.setMinimumWidth(0)
            host.updateGeometry()
        except RuntimeError:
            pass
    window._fh6_backup_relayout_active = False
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
    _metrics.record(
        "backup.relayout.async_total",
        elapsed_ms,
        item_count=visible_cards,
        detail=f"chunk={_BACKUP_RELAYOUT_CHUNK}",
    )

    window._fh6_backup_thumbnail_refresh_pending = False
    QTimer.singleShot(0, lambda owner=window: _ORIGINAL_REFRESH_BACKUP_THUMBNAILS(owner))

    if bool(getattr(window, "_fh6_backup_finish_after_relayout", False)):
        window._fh6_backup_finish_after_relayout = False
        _ORIGINAL_LAZY_LOAD_FINISHED(window)


def _smooth_relayout_backup(window: Any) -> None:
    layout = getattr(window, "backup_grid_layout", None)
    if layout is None:
        return

    generation = int(getattr(window, "_fh6_backup_relayout_generation", 0) or 0) + 1
    window._fh6_backup_relayout_generation = generation
    window._fh6_backup_relayout_active = True
    started_ns = time.perf_counter_ns()
    _stop_relayout_timer(window)

    # Clearing a QGridLayout is cheap in current measurements; the expensive
    # path is repeated add/show/width work. Keep clear/filter/group planning
    # synchronous, then time-slice the actual widget placement.
    try:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
        for header in getattr(window, "_fh6_backup_headers", {}).values():
            header.hide()

        needle = window.backup_search.text().strip().casefold()
        cards = [
            card
            for card in getattr(window, "_fh6_backup_cards", [])
            if (not needle or needle in str(card.property("searchText") or ""))
            and _backup_ui._backup_filter_allows(window, card)
        ]
        columns = _backup_ui._backup_columns(window)
        for column in range(GRID_MAX_COLUMNS):
            layout.setColumnStretch(column, 1 if column < columns else 0)

        placements: list[tuple[Any, int, int, int, int, bool]] = []
        mode = getattr(window, "_fh6_backup_group_mode", "none")
        if mode == "none":
            for index, card in enumerate(cards):
                placements.append((card, index // columns, index % columns, 1, 1, True))
        else:
            prop = "creatorGroupKey" if mode == "creator" else "vehicleGroupKey"
            label_prop = "creatorGroupLabel" if mode == "creator" else "vehicleGroupLabel"
            grouped: dict[str, list[Any]] = {}
            labels: dict[str, str] = {}
            for card in cards:
                key = str(card.property(prop) or "unknown")
                grouped.setdefault(key, []).append(card)
                labels.setdefault(key, str(card.property(label_prop) or "—"))
            row = 0
            for key, group_cards in grouped.items():
                label = labels[key]
                title = _backup_ui._txt(
                    f"{label} · 리버리 {len(group_cards)}개",
                    f"{label} · {len(group_cards)} liveries",
                )
                header = _backup_ui._group_header(window, f"{mode}:{key}", title)
                placements.append((header, row, 0, 1, columns, False))
                row += 1
                for index, card in enumerate(group_cards):
                    placements.append((card, row + index // columns, index % columns, 1, 1, True))
                row += (len(group_cards) + columns - 1) // columns
    except RuntimeError:
        window._fh6_backup_relayout_active = False
        if bool(getattr(window, "_fh6_backup_finish_after_relayout", False)):
            window._fh6_backup_finish_after_relayout = False
            _ORIGINAL_LAZY_LOAD_FINISHED(window)
        return

    card_width = _backup_card_width(window, columns)
    state = {"index": 0}
    timer = QTimer(window)
    timer.setInterval(1)
    window._fh6_backup_relayout_timer = timer

    def place_chunk() -> None:
        if generation != int(getattr(window, "_fh6_backup_relayout_generation", 0) or 0):
            _stop_relayout_timer(window)
            return

        start = state["index"]
        end = min(len(placements), start + _BACKUP_RELAYOUT_CHUNK)
        chunk_started = time.perf_counter_ns()
        try:
            for index in range(start, end):
                widget, row, column, row_span, column_span, is_card = placements[index]
                if is_card and card_width is not None:
                    widget.setMinimumWidth(0)
                    widget.setMaximumWidth(card_width)
                    widget.setFixedWidth(card_width)
                layout.addWidget(widget, row, column, row_span, column_span)
                widget.show()
        except RuntimeError:
            _finish_relayout(window, generation, started_ns, len(cards))
            return

        if _metrics.is_enabled():
            _metrics.add_sample(
                "backup.relayout.chunk",
                (time.perf_counter_ns() - chunk_started) / 1_000_000.0,
            )

        dialog = getattr(window, "_fh6_backup_loading_dialog", None)
        if dialog is not None and hasattr(dialog, "setLabelText"):
            try:
                placed_cards = min(len(cards), sum(1 for item in placements[:end] if item[5]))
                dialog.setLabelText(
                    _backup_ui._txt(
                        f"백업 화면을 배치하는 중... {placed_cards}/{len(cards)}",
                        f"Laying out backup view... {placed_cards}/{len(cards)}",
                    )
                )
            except RuntimeError:
                pass

        if end < len(placements):
            state["index"] = end
            return
        _finish_relayout(window, generation, started_ns, len(cards))

    if not placements:
        _finish_relayout(window, generation, started_ns, 0)
        return
    timer.timeout.connect(place_chunk)
    timer.start()


def apply_v1_3_4_backup_loading_resilience_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_loading_resilience_patched", False):
        return

    # One card per timer tick gives the event loop a natural repaint opportunity
    # without introducing QApplication.processEvents() into every card build.
    _lazy._CARD_BUILD_CHUNK = _BACKUP_CARD_BUILD_CHUNK

    # Existing long livery/tuning loops already use _yield_busy_events(). A
    # ~30-Hz cadence makes their indeterminate busy indicator less visibly stale.
    _responsive._BUSY_YIELD_INTERVAL_SECONDS = _BUSY_YIELD_INTERVAL_SECONDS
    _responsive._BUSY_PROCESS_EVENTS_MS = _BUSY_PROCESS_EVENTS_MS

    # Time-slice the expensive final backup grid placement and suppress the
    # legacy whole-grid width/thumbnail passes until the placement is complete.
    _backup_ui._relayout_backup = _smooth_relayout_backup
    _backup_ui._sync_backup_widths = _stable_sync_backup_widths
    _backup_ui._refresh_backup_thumbnails = _stable_refresh_backup_thumbnails
    _lazy._load_finished = _deferred_load_finished

    _lazy._start_full_load = _stable_start_full_load
    _bridge._safe_start_full_load = _stable_start_full_load
    MainWindow._fh6_v134_backup_loading_resilience_patched = True
