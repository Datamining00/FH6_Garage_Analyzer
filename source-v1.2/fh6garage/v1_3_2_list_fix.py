from __future__ import annotations

from PySide6.QtCore import QTimer

from .models import LiveryRecord


def apply_v1_3_2_list_fixes(MainWindow) -> None:
    """Keep scan completion on the proven v1.3.1 My Designs path.

    The base UI calls QApplication.processEvents() while synchronous content is
    being rebuilt.  Scheduling auction-card timers from inside
    _populate_livery_table() therefore allows those timers to run re-entrantly
    before scan completion and before the busy overlay has been released.

    During the initial scan, expose only normal Livery records to the original
    v1.3.1 table/grid construction.  After _scan_finished() has completely
    returned, append SoulBound cards one per event-loop turn.  Every deferred
    card is immediately parented to livery_grid_host so it can never become an
    accidental top-level window while waiting for final layout.
    """
    if getattr(MainWindow, "_fh6_v132_list_fix_patched", False):
        return

    combined_sorted_saved_content = MainWindow._sorted_saved_content
    original_populate_livery_table = MainWindow._populate_livery_table
    original_record_for_content_key = MainWindow._record_for_content_key
    original_duplicate_livery_hashes = MainWindow._duplicate_livery_hashes

    def patched_sorted_saved_content(self, content_type: str):
        records = combined_sorted_saved_content(self, content_type)
        if (
            content_type == "livery"
            and getattr(self, "_fh6_v132_initial_scan_build", False)
        ):
            # Initial scan invariant: use the exact My Designs content scope
            # handled successfully by v1.3.1. SoulBound is added only after
            # _scan_finished() returns to the outer event loop.
            return [
                record
                for record in records
                if not isinstance(record, LiveryRecord)
                or record.kind == "Livery"
            ]
        return records

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

        # This function is called only after initial scan completion.  The
        # combined v1.3.2 sorter now sees both enabled sources again.
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

            for card in self._livery_grid_cards:
                key = str(card.property("annotationKey") or "")
                if key and key not in seen:
                    ordered_cards.append(card)
                    seen.add(key)
            self._livery_grid_cards[:] = ordered_cards

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
            card = None
            try:
                key = self._content_annotation_key("livery", record)
                if key not in self._livery_card_by_key:
                    annotation = self.annotations.get(key)
                    card = self._make_livery_card(record, key)

                    # Critical Windows fix: _make_saved_content_card() creates a
                    # parentless QFrame.  The original synchronous grid reparents
                    # it before the event loop matters.  Deferred auction cards
                    # must be parented immediately before this callback returns.
                    card.setParent(self.livery_grid_host)
                    card.hide()

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
            except Exception as exc:  # noqa: BLE001 - isolate one malformed card
                if card is not None:
                    card.hide()
                    card.deleteLater()
                self._fh6_v132_auction_card_errors.append(
                    (
                        record.container_name,
                        f"{type(exc).__name__}: {exc}",
                    )
                )

            QTimer.singleShot(0, append_next)

        QTimer.singleShot(0, append_next)

    def patched_populate_livery_table(self) -> None:
        # Any explicit rebuild invalidates an older deferred append.  Do not
        # schedule from here: this function is called from inside synchronous
        # busy sections that themselves process Qt events.
        self._fh6_v132_auction_build_generation = (
            getattr(self, "_fh6_v132_auction_build_generation", 0) + 1
        )
        original_populate_livery_table(self)

    MainWindow._sorted_saved_content = patched_sorted_saved_content
    MainWindow._record_for_content_key = patched_record_for_content_key
    MainWindow._duplicate_livery_hashes = patched_duplicate_livery_hashes
    MainWindow._populate_livery_table = patched_populate_livery_table
    MainWindow._fh6_v132_schedule_auction_cards = schedule_auction_cards
    MainWindow._fh6_v132_list_fix_patched = True
