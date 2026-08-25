from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QThread, QTimer

from .auction_thumbnails import (
    AuctionThumbnailManifestError,
    AuctionThumbnailMatchStats,
    ManifestThumbnailEntry,
    _header_livery_token,
    container_download_timestamp,
    is_thumbnail_cache_dir,
    read_thumbnail_manifest,
)
from .models import LiveryRecord, TuningRecord
from .performance_metrics import write_latest_performance
from .saved_content_cards import rebuild_record_indexes
from .ui import MainWindow as _UiMainWindow

# Capture the original Qt-decorated slot before any runtime monkey patches are
# applied. v1.3.2 previously replaced this method with plain Python functions,
# which caused ScanWorker.finished to invoke UI rebuild code in the worker thread.
_ORIGINAL_SCAN_FINISHED = _UiMainWindow._scan_finished


def assign_auction_thumbnails(
    records: Iterable[LiveryRecord],
    cache_dir: Path | None,
) -> AuctionThumbnailMatchStats:
    """Resolve SoulBound thumbnails using exact identity and existing cache files.

    The manifest can retain several rows for the same CarOrdinal + livery token
    when the same livery has been rendered for multiple vehicle instances. Those
    stale/history rows are not ambiguous if only one referenced GUID.webp still
    exists in the selected CacheThumbnails directory.

    Resolution therefore proceeds in this order:
      1. exact CarOrdinal + header-derived livery token,
      2. keep only manifest rows whose GUID.webp currently exists,
      3. use the result only when exactly one existing file remains.

    If two or more matching WebPs still exist, no arbitrary instance is chosen.
    """
    auction_records = [
        record for record in records if record.kind == "SoulBoundLivery"
    ]
    for record in auction_records:
        embedded = container_download_timestamp(record.container_name)
        if embedded is not None:
            record.downloaded_at = embedded
        record.thumbnail_path = None

    if (
        not auction_records
        or cache_dir is None
        or not is_thumbnail_cache_dir(cache_dir)
    ):
        return AuctionThumbnailMatchStats(
            auction_count=len(auction_records),
            unmatched=len(auction_records),
        )

    try:
        entries = read_thumbnail_manifest(Path(cache_dir))
    except AuctionThumbnailManifestError:
        return AuctionThumbnailMatchStats(
            auction_count=len(auction_records),
            unmatched=len(auction_records),
        )

    by_identity: dict[tuple[int, str], list[ManifestThumbnailEntry]] = {}
    for entry in entries:
        if not entry.livery_token:
            continue
        by_identity.setdefault(
            (entry.car_id, entry.livery_token),
            [],
        ).append(entry)

    matched = 0
    ambiguous = 0

    for record in auction_records:
        if record.car_id is None:
            continue
        token = _header_livery_token(record)
        if not token:
            continue

        candidates = by_identity.get((int(record.car_id), token), [])
        existing_candidates = [
            entry for entry in candidates if entry.path.is_file()
        ]

        if len(existing_candidates) != 1:
            if len(existing_candidates) > 1:
                ambiguous += 1
            continue

        record.thumbnail_path = existing_candidates[0].path
        matched += 1

    return AuctionThumbnailMatchStats(
        auction_count=len(auction_records),
        matched_by_header_id=matched,
        ambiguous=ambiguous,
        unmatched=max(0, len(auction_records) - matched),
    )


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

    def patched_populate_all(self) -> None:
        ui_started = perf_counter()
        result = self.result
        if result is not None:
            try:
                cache_getter = getattr(self, "_fh6_v132_current_cache_path", None)
                cache_path = cache_getter() if callable(cache_getter) else None
                self._fh6_v132_match_stats = assign_auction_thumbnails(
                    result.liveries,
                    cache_path,
                )
            except Exception:  # noqa: BLE001 - optional cache integration
                # Cache integration is optional and must never block save loading.
                self._fh6_v132_match_stats = None

        rebuild_record_indexes(self)

        # The synchronous initial build must remain identical in scope to 1.3.1:
        # only normal My Designs records are exposed to the existing table/grid.
        self._fh6_v132_initial_scan_build = True
        try:
            current_populate_all(self)
        finally:
            self._fh6_v132_initial_scan_build = False

        # _populate_all() is running inside the original Qt slot on the GUI
        # thread. Queue SoulBound card append until the original _scan_finished
        # completes its busy-overlay cleanup and returns to the event loop.
        scheduler = getattr(self, "_fh6_v132_schedule_auction_cards", None)
        if callable(scheduler):
            QTimer.singleShot(0, scheduler)

        ui_timings = {
            "ui.scan_result_to_initial_paint": round(
                (perf_counter() - ui_started) * 1000.0,
                3,
            )
        }
        indexes = getattr(self, "_fh6_record_by_key", {})
        counters = {
            "gui_thread_confirmed": QThread.currentThread() is self.thread(),
            "livery_index_entries": len(indexes.get("livery", {})),
            "tuning_index_entries": len(indexes.get("tuning", {})),
            "livery_cards_created": getattr(
                self, "_fh6_ui_livery_cards_created", 0
            ),
            "livery_cards_reused": getattr(
                self, "_fh6_ui_livery_cards_reused", 0
            ),
            "tuning_cards_created": getattr(
                self, "_fh6_ui_tuning_cards_created", 0
            ),
            "tuning_cards_reused": getattr(
                self, "_fh6_ui_tuning_cards_reused", 0
            ),
            "cards_discarded": getattr(self, "_fh6_ui_cards_discarded", 0),
        }
        pixmaps = getattr(self, "_fh6_thumbnail_pixmap_cache", None)
        if pixmaps is not None and hasattr(pixmaps, "stats"):
            counters.update(pixmaps.stats())
        view_operations = getattr(self, "_view_operations", None)
        if view_operations is not None and hasattr(view_operations, "stats"):
            counters.update(view_operations.stats())
        refresh_diff = getattr(self, "_fh6_latest_livery_diff", None)
        if refresh_diff is not None:
            counters.update(
                {
                    "refresh_thumbnail_cache_files": getattr(
                        refresh_diff, "cache_files", 0
                    ),
                    "refresh_thumbnail_cache_bytes": getattr(
                        refresh_diff, "cache_bytes", 0
                    ),
                    "refresh_cache_cleanup_removed_files": getattr(
                        refresh_diff, "cleanup_removed_files", 0
                    ),
                    "refresh_cache_cleanup_removed_bytes": getattr(
                        refresh_diff, "cleanup_removed_bytes", 0
                    ),
                }
            )
        write_latest_performance(
            {
                "app_version": "1.3.2",
                "scan": getattr(result, "diagnostics", {}),
                "ui": {
                    "timings_ms": ui_timings,
                    "counters": counters,
                },
            }
        )

    MainWindow._populate_all = patched_populate_all

    # Critical fix: restore the exact class-defined @Slot(object) method.
    # Do not wrap or redecorate it dynamically; preserving the original slot
    # keeps Qt AutoConnection queued to the MainWindow/GUI thread.
    MainWindow._scan_finished = _ORIGINAL_SCAN_FINISHED
    MainWindow._fh6_v132_thread_affinity_fixed = True
