from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QTimer

from .auction_thumbnails import assign_auction_thumbnails
from .models import LiveryRecord
from .ui import MainWindow as _UiMainWindow


# Capture the original Qt-decorated slot before any runtime monkey patches are
# applied.  v1.3.2 previously replaced this method with plain Python functions,
# which caused ScanWorker.finished to invoke UI rebuild code in the worker thread.
_ORIGINAL_SCAN_FINISHED = _UiMainWindow._scan_finished


def apply_v1_3_2_thread_affinity_fix(MainWindow) -> None:
    """Restore GUI-thread scan completion and move v1.3.2 work into _populate_all.

    The original ui.MainWindow._scan_finished method is decorated with
    @Slot(object), so Qt queues ScanWorker.finished to the MainWindow thread.
    Replacing that slot with ordinary Python callables breaks that guarantee.

    Restore the exact original slot and perform the v1.3.2 thumbnail/index/list
    preparation from _populate_all(), which is called by that original slot after
    self.result has already been assigned on the GUI thread.
    """
    if getattr(MainWindow, "_fh6_v132_thread_affinity_fixed", False):
        return

    current_populate_all = MainWindow._populate_all

    def _rebuild_v132_indexes(self) -> None:
        result = self.result
        if result is None:
            self._fh6_v132_livery_record_by_key = {}
            self._fh6_v132_duplicate_hashes = set()
            return

        by_key: dict[str, LiveryRecord] = {}
        for record in result.liveries:
            if record.kind not in {"Livery", "SoulBoundLivery"}:
                continue
            key = self._content_annotation_key("livery", record)
            by_key[key] = record
        self._fh6_v132_livery_record_by_key = by_key

        counts = Counter(
            record.content_sha256
            for record in result.liveries
            if record.kind == "Livery" and record.content_sha256
        )
        self._fh6_v132_duplicate_hashes = {
            digest for digest, count in counts.items() if count > 1
        }

    def patched_populate_all(self) -> None:
        result = self.result
        if result is not None:
            try:
                cache_getter = getattr(self, "_fh6_v132_current_cache_path", None)
                cache_path = cache_getter() if callable(cache_getter) else None
                self._fh6_v132_match_stats = assign_auction_thumbnails(
                    result.liveries,
                    cache_path,
                )
            except Exception:
                # Cache integration is optional and must never block save loading.
                self._fh6_v132_match_stats = None

        _rebuild_v132_indexes(self)

        # The synchronous initial build must remain identical in scope to 1.3.1:
        # only normal My Designs records are exposed to the existing table/grid.
        self._fh6_v132_initial_scan_build = True
        try:
            current_populate_all(self)
        finally:
            self._fh6_v132_initial_scan_build = False

        # _populate_all() is running inside the original Qt slot on the GUI
        # thread.  Queue SoulBound card append until the original _scan_finished
        # completes its busy-overlay cleanup and returns to the event loop.
        scheduler = getattr(self, "_fh6_v132_schedule_auction_cards", None)
        if callable(scheduler):
            QTimer.singleShot(0, scheduler)

    MainWindow._populate_all = patched_populate_all

    # Critical fix: restore the exact class-defined @Slot(object) method.
    # Do not wrap or redecorate it dynamically; preserving the original slot
    # keeps Qt AutoConnection queued to the MainWindow/GUI thread.
    MainWindow._scan_finished = _ORIGINAL_SCAN_FINISHED
    MainWindow._fh6_v132_thread_affinity_fixed = True
