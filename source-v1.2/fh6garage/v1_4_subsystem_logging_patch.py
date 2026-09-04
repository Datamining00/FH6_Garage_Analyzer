from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread

from .subsystem_log import log_event
from . import ui as _ui
from . import v1_3_2_memory_state_patch as _memory
from . import v1_3_2_performance_profiler as _profiler
from . import v1_3_2_scan_postprocessing as _post


def apply_v1_4_subsystem_logging_patch(MainWindow: Any) -> None:
    """Install non-blocking subsystem diagnostics without changing behavior."""
    if getattr(MainWindow, "_fh6_v14_subsystem_logging_patched", False):
        return

    original_scan = _ui.scan_save
    def logged_scan(*args, **kwargs):
        log_event("SCAN", "scan.start", backend=kwargs.get("backend", "auto"))
        try:
            result = original_scan(*args, **kwargs)
        except Exception as exc:
            log_event("SCAN", "scan.failed", error=type(exc).__name__)
            raise
        log_event(
            "SCAN", "scan.complete",
            liveries=len(result.liveries),
            tunings=len(result.tunings),
            warnings=len(result.warnings),
        )
        return result
    _ui.scan_save = logged_scan

    original_nav = _ui.send_arrow_keys_to_fh6
    def logged_nav(keys, interval=0.07, *, auto_activate=True):
        log_event("NAVIGATION", "navigation.start", moves=len(keys), auto_activate=auto_activate)
        try:
            title = original_nav(keys, interval, auto_activate=auto_activate)
        except Exception as exc:
            log_event("NAVIGATION", "navigation.failed", error=type(exc).__name__)
            raise
        log_event("NAVIGATION", "navigation.complete", moves=len(keys))
        return title
    _ui.send_arrow_keys_to_fh6 = logged_nav

    original_memory_finished = _memory._on_memory_finished
    def logged_memory_finished(window, result):
        log_event(
            "MEMORY", "memory.finished",
            usable=getattr(result, "usable", False),
            status=getattr(result, "status", type(result).__name__),
        )
        return original_memory_finished(window, result)
    _memory._on_memory_finished = logged_memory_finished

    original_memory_failed = _memory._on_memory_failed
    def logged_memory_failed(window, message, *, already_finished=False):
        log_event("MEMORY", "memory.failed", error="scan_failure")
        return original_memory_failed(window, message, already_finished=already_finished)
    _memory._on_memory_failed = logged_memory_failed

    original_thumbnail = _post._prepare_v132_auction_thumbnails
    def logged_thumbnail(window, result):
        try:
            return original_thumbnail(window, result)
        finally:
            stats = getattr(window, "_fh6_v132_match_stats", None)
            log_event(
                "THUMBNAIL", "thumbnail.prepare",
                matched=getattr(stats, "matched_by_header_id", None),
                unmatched=getattr(stats, "unmatched", None),
            )
    _post._prepare_v132_auction_thumbnails = logged_thumbnail

    original_index = _post._rebuild_v132_indexes_with_metrics
    def logged_index(window, result):
        try:
            return original_index(window, result)
        finally:
            indexes = getattr(window, "_fh6_record_by_key", {})
            log_event(
                "INDEX", "index.rebuild",
                liveries=len(indexes.get("livery", {})),
                tunings=len(indexes.get("tuning", {})),
            )
    _post._rebuild_v132_indexes_with_metrics = logged_index

    original_populate = MainWindow._populate_all
    def logged_populate(self):
        gui_thread = QThread.currentThread() is self.thread()
        log_event("THREAD", "populate.thread", gui_thread=gui_thread)
        log_event("POPULATE", "populate.start")
        try:
            return original_populate(self)
        finally:
            log_event("POPULATE", "populate.complete")
    MainWindow._populate_all = logged_populate

    original_performance_write = _profiler.write_latest_performance
    def logged_performance_write(payload):
        path = original_performance_write(payload)
        log_event("PERFORMANCE", "performance.snapshot", written=path is not None)
        return path
    _profiler.write_latest_performance = logged_performance_write

    MainWindow._fh6_v14_subsystem_logging_patched = True
