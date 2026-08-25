from __future__ import annotations

from collections.abc import Callable, Iterable
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
from .models import LiveryRecord
from .performance_metrics import write_latest_performance
from .saved_content_cards import rebuild_record_indexes


def assign_auction_thumbnails(
    records: Iterable[LiveryRecord],
    cache_dir: Path | None,
) -> AuctionThumbnailMatchStats:
    """Match auction records to existing thumbnails without guessing."""
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
        if entry.livery_token:
            by_identity.setdefault((entry.car_id, entry.livery_token), []).append(entry)

    matched = 0
    ambiguous = 0
    for record in auction_records:
        if record.car_id is None:
            continue
        token = _header_livery_token(record)
        if not token:
            continue
        existing = [
            entry
            for entry in by_identity.get((int(record.car_id), token), [])
            if entry.path.is_file()
        ]
        if len(existing) != 1:
            ambiguous += int(len(existing) > 1)
            continue
        record.thumbnail_path = existing[0].path
        matched += 1

    return AuctionThumbnailMatchStats(
        auction_count=len(auction_records),
        matched_by_header_id=matched,
        ambiguous=ambiguous,
        unmatched=max(0, len(auction_records) - matched),
    )


def populate_scan_result_ui(owner: object, populate_content: Callable[[], None]) -> None:
    """Prepare and measure a scan result while execution is on the GUI thread."""
    ui_started = perf_counter()
    result = getattr(owner, "result", None)
    if result is not None:
        try:
            cache_getter = getattr(owner, "_fh6_v132_current_cache_path", None)
            cache_path = cache_getter() if callable(cache_getter) else None
            owner._fh6_v132_match_stats = assign_auction_thumbnails(  # type: ignore[attr-defined]
                result.liveries,
                cache_path,
            )
        except Exception:  # noqa: BLE001 - cache integration is optional
            owner._fh6_v132_match_stats = None  # type: ignore[attr-defined]

    rebuild_record_indexes(owner)
    owner._fh6_v132_initial_scan_build = True  # type: ignore[attr-defined]
    try:
        populate_content()
    finally:
        owner._fh6_v132_initial_scan_build = False  # type: ignore[attr-defined]

    scheduler = getattr(owner, "_fh6_v132_schedule_auction_cards", None)
    if callable(scheduler):
        QTimer.singleShot(0, scheduler)

    indexes = getattr(owner, "_fh6_record_by_key", {})
    counters = {
        "gui_thread_confirmed": QThread.currentThread() is owner.thread(),  # type: ignore[attr-defined]
        "livery_index_entries": len(indexes.get("livery", {})),
        "tuning_index_entries": len(indexes.get("tuning", {})),
        "livery_cards_created": getattr(owner, "_fh6_ui_livery_cards_created", 0),
        "livery_cards_reused": getattr(owner, "_fh6_ui_livery_cards_reused", 0),
        "tuning_cards_created": getattr(owner, "_fh6_ui_tuning_cards_created", 0),
        "tuning_cards_reused": getattr(owner, "_fh6_ui_tuning_cards_reused", 0),
        "cards_discarded": getattr(owner, "_fh6_ui_cards_discarded", 0),
    }
    pixmaps = getattr(owner, "_fh6_thumbnail_pixmap_cache", None)
    if pixmaps is not None and hasattr(pixmaps, "stats"):
        counters.update(pixmaps.stats())
    view_operations = getattr(owner, "_view_operations", None)
    if view_operations is not None and hasattr(view_operations, "stats"):
        counters.update(view_operations.stats())
    refresh_diff = getattr(owner, "_fh6_latest_livery_diff", None)
    if refresh_diff is not None:
        counters.update(
            {
                "refresh_thumbnail_cache_files": getattr(refresh_diff, "cache_files", 0),
                "refresh_thumbnail_cache_bytes": getattr(refresh_diff, "cache_bytes", 0),
                "refresh_cache_cleanup_removed_files": getattr(refresh_diff, "cleanup_removed_files", 0),
                "refresh_cache_cleanup_removed_bytes": getattr(refresh_diff, "cleanup_removed_bytes", 0),
            }
        )
    write_latest_performance(
        {
            "app_version": "1.4.0-alpha.1",
            "scan": getattr(result, "diagnostics", {}),
            "ui": {
                "timings_ms": {
                    "ui.scan_result_to_initial_paint": round(
                        (perf_counter() - ui_started) * 1000.0,
                        3,
                    )
                },
                "counters": counters,
            },
        }
    )
