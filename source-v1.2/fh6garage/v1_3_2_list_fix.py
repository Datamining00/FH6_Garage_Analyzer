from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QTimer

from .models import LiveryRecord


def apply_v1_3_2_list_fixes(MainWindow) -> None:
    """Keep startup on the proven v1.3.1 My Designs path.

    v1.3.1 already handles the user's large My Designs collection.  Feeding
    SoulBound records through the same synchronous scan-complete turn pushes
    additional heavy QWidget construction into the busy startup path.  Build
    the normal My Designs table/grid exactly as before, let scan completion
    return to the Windows event loop, and then append only the auction cards one
    at a time.  A malformed/problematic auction record therefore cannot block
    the complete livery page or leave startup permanently at "rebuilding".

    The hidden table remains My-Designs-only.  The visible card grid receives
    auction records after startup and is finally reordered to the selected
    combined sort order.  Pure per-card lookups are cached per ScanResult.
    """
    if getattr(MainWindow, "_fh6_v132_list_fix_patched", False):
        return

    original_scan_finished = MainWindow._scan_finished
    # At this point v1_3_2_patch has already replaced _sorted_saved_content.
    # Keep that combined sorter privately, while exposing a My-Designs-only
    # sorter to the synchronous v1.3.1 table/grid construction path.
    combined_sorted_saved_content = MainWindow._sorted_saved_content
    original_populate_livery_table = MainWindow._populate_livery_table
    original_record_for_content_key = MainWindow._record_for_content_key
    original_duplicate_livery_hashes = MainWindow._duplicate_livery_hashes

    def rebuild_indexes(self, result) -> None:
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

    def patched_scan_finished(self, result) -> None:
        rebuild_indexes(self, result)
        original_scan_finished(self, result)

    def patched_sorted_saved_content(self, content_type: str):
        records = combined_sorted_saved_content(self, content_type)
        if content_type != "livery":
            return records
        # Critical startup invariant: the synchronous v1.3.1 construction path
        # never sees SoulBound records. Auction cards are appended after that
        # path has completed and the event loop is free again.
        return [
            record
            for record in records
            if not isinstance(record, LiveryRecord) or record.kind == "Livery"
        ]

    def patched_record_for_content_key(self, content_type: str, key: str):
        if content_type == "livery":
            index = getattr(self, "_fh6_v132_livery_record_by_key", None)
            if isinstance(index, dict):
                record = index.get(key)
                if record is not None:
                    return record
        return original_record_for_content_key(self, content_type, key)

    def patched_duplicate_livery_hashes(self) -> set[str]:
        cached = getattr(self, "_fh6_v132_duplicate_hashes", None)
        if isinstance(cached, set):
            return cached
        return original_duplicate_livery_hashes(self)

    def schedule_auction_cards(self) -> None:
        generation = getattr(self, "_fh6_v132_auction_build_generation", 0) + 1
        self._fh6_v132_auction_build_generation = generation
        self._fh6_v132_auction_card_errors = []

        if self.result is None:
            return

        # Use the v1.3.2 combined sorter captured before this patch. It already
        # honours source toggles and the selected sort mode.
        combined_records = list(combined_sorted_saved_content(self, "livery"))
        auction_records = [
            record
            for record in combined_records
            if isinstance(record, LiveryRecord)
            and record.kind == "SoulBoundLivery"
        ]
        if not auction_records:
            return

        state = {"index": 0}

        def finish() -> None:
            if generation != getattr(
                self, "_fh6_v132_auction_build_generation", generation
            ):
                return

            # Match the currently selected combined sort order without rebuilding
            # the already-created My Designs cards.
            current_records = list(combined_sorted_saved_content(self, "livery"))
            ordered_cards = []
            seen = set()
            for record in current_records:
                if not isinstance(record, LiveryRecord):
                    continue
                key = self._content_annotation_key("livery", record)
                card = self._livery_card_by_key.get(key)
                if card is not None and key not in seen:
                    ordered_cards.append(card)
                    seen.add(key)
            # Defensive fallback for any card not represented by the current
            # sorter (for example if a preference changed during a timer turn).
            for card in self._livery_grid_cards:
                key = str(card.property("annotationKey") or "")
                if key and key not in seen:
                    ordered_cards.append(card)
                    seen.add(key)
            self._livery_grid_cards[:] = ordered_cards

            # One layout/filter pass after all auction cards exist. Thumbnail
            # decoding remains the existing lazy visible-card path.
            self._filter_livery_views(
                self.livery_search.text(),
                preserve_scroll=True,
            )
            self._apply_pointing_cursors(self.livery_grid_host)

        def append_next() -> None:
            if generation != getattr(
                self, "_fh6_v132_auction_build_generation", generation
            ):
                return
            if self.result is None:
                return

            index = state["index"]
            if index >= len(auction_records):
                finish()
                return

            record = auction_records[index]
            state["index"] = index + 1
            try:
                key = self._content_annotation_key("livery", record)
                # Do not duplicate a card if a rapid rebuild/toggle already
                # produced it in a newer UI state.
                if key not in self._livery_card_by_key:
                    annotation = self.annotations.get(key)
                    card = self._make_livery_card(record, key)
                    card.setProperty(
                        "searchText",
                        self._livery_search_text(record, annotation.note),
                    )
                    card.setProperty("annotationKey", key)
                    card.setProperty(
                        "vehicleGroupKey",
                        f"id:{record.car_id}"
                        if record.car_id is not None
                        else "unknown",
                    )
                    card.setProperty(
                        "vehicleGroupLabel",
                        self._car_label(record.car_id),
                    )
                    creator_label = (
                        (record.header.creator or "").strip()
                        or "—"
                    )
                    card.setProperty(
                        "creatorGroupKey",
                        f"creator:{creator_label.casefold()}",
                    )
                    card.setProperty("creatorGroupLabel", creator_label)
                    card.setProperty("checked", annotation.checked)
                    card.setProperty("triangle", annotation.triangle)
                    card.setProperty("excluded", annotation.excluded)
                    self._livery_grid_cards.append(card)
                    self._livery_card_by_key[key] = card
            except Exception as exc:
                # One corrupt/unsupported SoulBound entry must never wedge the
                # complete livery list. Retain diagnostics for inspection while
                # continuing with the remaining auction records.
                self._fh6_v132_auction_card_errors.append(
                    (
                        record.container_name,
                        f"{type(exc).__name__}: {exc}",
                    )
                )

            # Exactly one auction card per event-loop turn. This is intentionally
            # different from the removed all-record batching experiment: the
            # proven My Designs grid is already complete before this begins.
            QTimer.singleShot(0, append_next)

        QTimer.singleShot(0, append_next)

    def patched_populate_livery_table(self) -> None:
        # Invalidate any older asynchronous auction append before the original
        # v1.3.1 path clears/rebuilds its card collection.
        self._fh6_v132_auction_build_generation = (
            getattr(self, "_fh6_v132_auction_build_generation", 0) + 1
        )
        original_populate_livery_table(self)
        schedule_auction_cards(self)

    MainWindow._scan_finished = patched_scan_finished
    MainWindow._sorted_saved_content = patched_sorted_saved_content
    MainWindow._record_for_content_key = patched_record_for_content_key
    MainWindow._duplicate_livery_hashes = patched_duplicate_livery_hashes
    MainWindow._populate_livery_table = patched_populate_livery_table
    MainWindow._fh6_v132_schedule_auction_cards = schedule_auction_cards
    MainWindow._fh6_v132_list_fix_patched = True
