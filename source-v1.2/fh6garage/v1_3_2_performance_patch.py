from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QTimer

from .i18n import tr
from .models import LiveryRecord


_LIVERY_GRID_BATCH_SIZE = 12


def apply_v1_3_2_performance_patches(MainWindow) -> None:
    """Keep large livery collections responsive while their cards are built.

    v1.3.1 creates every livery card synchronously while the scan-complete slot is
    running. Adding SoulBound entries increases the number of heavy QWidget trees
    created in that single GUI turn. Build the grid in short event-loop batches
    and cache lookups that were previously repeated for every visible card.
    """
    if getattr(MainWindow, "_fh6_v132_performance_patched", False):
        return

    original_scan_finished = MainWindow._scan_finished
    original_record_for_content_key = MainWindow._record_for_content_key
    original_populate_saved_content_table = MainWindow._populate_saved_content_table

    def rebuild_livery_indexes(self, result) -> None:
        record_by_key: dict[str, LiveryRecord] = {}
        for record in result.liveries:
            if record.kind not in {"Livery", "SoulBoundLivery"}:
                continue
            key = self._content_annotation_key("livery", record)
            record_by_key[key] = record
        self._fh6_v132_record_by_key = record_by_key

        counts = Counter(
            record.content_sha256
            for record in result.liveries
            if record.kind == "Livery" and record.content_sha256
        )
        self._fh6_v132_duplicate_hashes_cache = {
            digest for digest, count in counts.items() if count > 1
        }

    def patched_scan_finished(self, result) -> None:
        rebuild_livery_indexes(self, result)
        original_scan_finished(self, result)

    def patched_record_for_content_key(self, content_type: str, key: str):
        if content_type == "livery":
            cached = getattr(self, "_fh6_v132_record_by_key", None)
            if isinstance(cached, dict):
                record = cached.get(key)
                if record is not None:
                    return record
        return original_record_for_content_key(self, content_type, key)

    def patched_duplicate_livery_hashes(self) -> set[str]:
        cached = getattr(self, "_fh6_v132_duplicate_hashes_cache", None)
        if cached is not None:
            return cached
        if self.result is None:
            return set()
        counts = Counter(
            record.content_sha256
            for record in self.result.liveries
            if record.kind == "Livery" and record.content_sha256
        )
        cached = {digest for digest, count in counts.items() if count > 1}
        self._fh6_v132_duplicate_hashes_cache = cached
        return cached

    def patched_populate_saved_content_table(self, content_type: str) -> None:
        # QTableWidget repaints/layouts after many individual insertions by
        # default. Suppress intermediate paints for the large livery table.
        if content_type != "livery" or not hasattr(self, "livery_table"):
            original_populate_saved_content_table(self, content_type)
            return
        table = self.livery_table
        table.setUpdatesEnabled(False)
        try:
            original_populate_saved_content_table(self, content_type)
        finally:
            table.setUpdatesEnabled(True)
            table.viewport().update()

    def patched_populate_livery_grid(self) -> None:
        # Cancel any unfinished build from a previous scan/sort/source toggle.
        generation = getattr(self, "_fh6_v132_livery_grid_generation", 0) + 1
        self._fh6_v132_livery_grid_generation = generation

        for card in self._livery_grid_cards:
            card.deleteLater()
        self._livery_grid_cards.clear()
        self._livery_card_by_key.clear()
        self._clear_livery_grid_layout()

        records = list(self._sorted_liveries())
        if not records:
            self._relayout_livery_grid(self.livery_search.text())
            return

        state = {"index": 0}

        def build_next_batch() -> None:
            if generation != getattr(
                self, "_fh6_v132_livery_grid_generation", generation
            ):
                return

            start = state["index"]
            end = min(start + _LIVERY_GRID_BATCH_SIZE, len(records))

            for record in records[start:end]:
                key = self._annotation_key(record)
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
                card.setProperty("vehicleGroupLabel", self._car_label(record.car_id))
                creator_label = (record.header.creator or "").strip() or tr(
                    "creator.none"
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

            state["index"] = end
            if end < len(records):
                # Yield to the Windows message pump between small batches. This
                # prevents Explorer from reporting the GUI as Not Responding.
                QTimer.singleShot(0, build_next_batch)
                return

            if generation != getattr(
                self, "_fh6_v132_livery_grid_generation", generation
            ):
                return
            self._relayout_livery_grid(self.livery_search.text())
            self._apply_pointing_cursors(self.livery_grid_host)
            self._show_status(
                f"{tr('content.noun_livery')} {len(records)}",
                1500,
            )

        # Let the scan-complete slot return first; the dashboard becomes usable
        # immediately and the livery grid then fills in without a long GUI stall.
        QTimer.singleShot(0, build_next_batch)

    MainWindow._scan_finished = patched_scan_finished
    MainWindow._record_for_content_key = patched_record_for_content_key
    MainWindow._duplicate_livery_hashes = patched_duplicate_livery_hashes
    MainWindow._populate_saved_content_table = patched_populate_saved_content_table
    MainWindow._populate_livery_grid = patched_populate_livery_grid
    MainWindow._fh6_v132_performance_patched = True
