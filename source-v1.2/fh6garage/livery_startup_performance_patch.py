from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from .livery_hash_cache import cache_key, enrich_sha256, lookup_cached_sha256
from .performance_metrics import record_metric


_APPLIED = False


class _HashEnrichmentWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, paths: list[Path]):
        super().__init__()
        self.paths = paths

    @Slot()
    def run(self) -> None:
        started = time.perf_counter()
        try:
            thread = QThread.currentThread()
            mapping, stats = enrich_sha256(
                self.paths,
                should_stop=thread.isInterruptionRequested,
            )
            stats = dict(stats)
            stats["duration_ms"] = (time.perf_counter() - started) * 1000.0
            self.finished.emit({"hashes": mapping, "stats": stats})
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def apply_livery_startup_performance_patch(MainWindow) -> None:
    """Remove full-file hashing from the blocking garage scan.

    Cached hashes are reused using only file stat metadata. Missing hashes are
    enriched later on a low-priority worker after the cards are already visible.
    """
    global _APPLIED
    if _APPLIED:
        return

    from . import scanner
    from . import ui

    # scan_save resolves this global at call time, so replacing it here removes
    # the O(total C_livery bytes) startup read without changing scanner.py.
    scanner._file_sha256 = lookup_cached_sha256

    original_scan_save = ui.scan_save

    def timed_scan_save(path, car_db):
        started = time.perf_counter()
        result = original_scan_save(path, car_db)
        duration_ms = (time.perf_counter() - started) * 1000.0
        cached_hashes = sum(1 for record in result.liveries if record.content_sha256)
        record_metric(
            "startup_scan",
            duration_ms,
            livery_count=len(result.liveries),
            tuning_count=len(result.tunings),
            cached_hashes=cached_hashes,
            missing_hashes=max(0, len(result.liveries) - cached_hashes),
        )
        return result

    ui.scan_save = timed_scan_save

    original_scan_finished = MainWindow._scan_finished

    def _cleanup_hash_thread(self) -> None:
        self._fh6_hash_worker = None
        self._fh6_hash_thread = None

    def _refresh_after_hashes(self, source_result, payload) -> None:
        if self.result is not source_result:
            return
        mapping = dict(payload.get("hashes") or {})
        for record in source_result.liveries:
            if not record.livery_path:
                continue
            digest = mapping.get(cache_key(record.livery_path))
            if digest:
                record.content_sha256 = digest

        stats = dict(payload.get("stats") or {})
        record_metric(
            "background_livery_hashes",
            float(stats.pop("duration_ms", 0.0)),
            **stats,
        )

        # Duplicate filtering is the only user-facing feature that requires the
        # hashes. Refresh it only when that filter is active so enrichment does
        # not cause an unnecessary full card relayout.
        try:
            duplicate_active = 9 in self.livery_check_filter.selected_modes()
        except Exception:
            duplicate_active = False
        if duplicate_active and hasattr(self, "_filter_saved_content_views"):
            text = self.livery_search.text() if hasattr(self, "livery_search") else ""
            self._filter_saved_content_views("livery", text, preserve_scroll=True)

    def _start_hash_enrichment(self, source_result) -> None:
        if self.result is not source_result:
            return
        if getattr(self, "_fh6_hash_thread", None) is not None:
            return
        paths = [
            record.livery_path
            for record in source_result.liveries
            if record.livery_path is not None and not record.content_sha256
        ]
        if not paths:
            return

        thread = QThread(self)
        worker = _HashEnrichmentWorker(paths)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda payload, result=source_result: _refresh_after_hashes(self, result, payload))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: _cleanup_hash_thread(self))
        self._fh6_hash_thread = thread
        self._fh6_hash_worker = worker
        thread.start(QThread.Priority.LowPriority)

    def patched_scan_finished(self, result) -> None:
        started = time.perf_counter()
        original_scan_finished(self, result)
        record_metric(
            "startup_ui_population",
            (time.perf_counter() - started) * 1000.0,
            livery_count=len(result.liveries),
            tuning_count=len(result.tunings),
        )
        # Let the first visible cards and their already-lazy thumbnails settle
        # before background hashing begins.
        QTimer.singleShot(500, lambda source_result=result: _start_hash_enrichment(self, source_result))

    MainWindow._scan_finished = patched_scan_finished
    MainWindow._fh6_startup_performance_patch_applied = True
    _APPLIED = True
