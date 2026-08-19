from __future__ import annotations

import time
from collections import Counter

from PySide6.QtCore import QTimer

from .performance_metrics import record_metric
from .i18n import tr


_APPLIED = False
_FIRST_BATCH = 8
_INCREMENTAL_BATCH = 8
_RELAYOUT_EVERY = 32
_BATCH_BUDGET_MS = 18.0


def apply_livery_list_rebuild_performance_patch(MainWindow) -> None:
    """Keep large livery libraries responsive while rebuilding the card grid.

    Three independent costs are addressed here:

    * The hidden legacy QTableWidget is no longer rebuilt.
    * annotation-key lookup and duplicate-hash detection are cached instead of
      repeating O(n) work for every card.
    * Most importantly, hundreds of complex Qt card widgets are not constructed
      in one blocking main-thread loop.  A small first batch is created so the
      visible page can paint immediately, then the remaining cards are appended
      in short event-loop batches.  Generation tokens cancel stale batches when
      a refresh/sort starts another rebuild.
    """
    global _APPLIED
    if _APPLIED:
        return

    original_scan_finished = MainWindow._scan_finished
    original_apply_pointing_cursors = MainWindow._apply_pointing_cursors

    def _invalidate_livery_lookup_caches(self) -> None:
        self._fh6_record_lookup_cache_result = None
        self._fh6_record_lookup_cache = {}
        self._fh6_duplicate_hashes_cache = None

    def _record_for_content_key(self, content_type: str, key: str):
        result = getattr(self, "result", None)
        if result is None or not key:
            return None

        cache_result = getattr(self, "_fh6_record_lookup_cache_result", None)
        cache = getattr(self, "_fh6_record_lookup_cache", None)
        if cache_result is not result or not isinstance(cache, dict):
            cache = {}
            for kind in ("livery", "tuning"):
                mapping = {}
                for record in self._saved_content_records(kind):
                    mapping[self._content_annotation_key(kind, record)] = record
                cache[kind] = mapping
            self._fh6_record_lookup_cache_result = result
            self._fh6_record_lookup_cache = cache

        return cache.get(content_type, {}).get(key)

    def _duplicate_livery_hashes(self) -> set[str]:
        cached = getattr(self, "_fh6_duplicate_hashes_cache", None)
        if cached is not None:
            return cached
        counts = Counter(
            record.content_sha256
            for record in self._custom_liveries()
            if record.content_sha256
        )
        duplicates = {digest for digest, count in counts.items() if count > 1}
        self._fh6_duplicate_hashes_cache = duplicates
        return duplicates

    def _append_livery_card(self, record) -> None:
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
            f"id:{record.car_id}" if record.car_id is not None else "unknown",
        )
        card.setProperty("vehicleGroupLabel", self._car_label(record.car_id))
        creator_label = (record.header.creator or "").strip() or tr("creator.none")
        card.setProperty("creatorGroupKey", f"creator:{creator_label.casefold()}")
        card.setProperty("creatorGroupLabel", creator_label)
        card.setProperty("checked", annotation.checked)
        card.setProperty("triangle", annotation.triangle)
        card.setProperty("excluded", annotation.excluded)
        self._livery_grid_cards.append(card)
        self._livery_card_by_key[key] = card

    def _finish_incremental_livery_grid(self, generation: int, started: float, total: int) -> None:
        if generation != getattr(self, "_fh6_livery_grid_generation", -1):
            return
        self._relayout_livery_grid(self.livery_search.text())
        self._fh6_livery_grid_building = False
        record_metric(
            "livery_list_rebuild_complete",
            (time.perf_counter() - started) * 1000.0,
            card_count=len(self._livery_grid_cards),
            expected_count=total,
            incremental=True,
        )

    def _continue_livery_grid(
        self,
        generation: int,
        source_result,
        records,
        next_index: int,
        started: float,
        since_layout: int,
    ) -> None:
        if generation != getattr(self, "_fh6_livery_grid_generation", -1):
            return
        if getattr(self, "result", None) is not source_result:
            return

        batch_started = time.perf_counter()
        created = 0
        index = next_index
        total = len(records)
        while index < total and created < _INCREMENTAL_BATCH:
            _append_livery_card(self, records[index])
            index += 1
            created += 1
            if (time.perf_counter() - batch_started) * 1000.0 >= _BATCH_BUDGET_MS:
                break

        since_layout += created
        if index >= total:
            _finish_incremental_livery_grid(self, generation, started, total)
            return

        # Re-layout only periodically. Repacking the whole grid after every tiny
        # batch would reintroduce an O(n^2)-like UI cost. The first batch is
        # already visible, and additional cards appear in coarse increments.
        if since_layout >= _RELAYOUT_EVERY:
            self._relayout_livery_grid(self.livery_search.text())
            since_layout = 0

        QTimer.singleShot(
            0,
            lambda: _continue_livery_grid(
                self,
                generation,
                source_result,
                records,
                index,
                started,
                since_layout,
            ),
        )

    def _populate_livery_grid(self) -> None:
        generation = int(getattr(self, "_fh6_livery_grid_generation", 0)) + 1
        self._fh6_livery_grid_generation = generation
        self._fh6_livery_grid_building = True

        for card in self._livery_grid_cards:
            card.deleteLater()
        self._livery_grid_cards.clear()
        self._livery_card_by_key.clear()
        self._clear_livery_grid_layout()

        records = list(self._sorted_liveries())
        source_result = getattr(self, "result", None)
        started = time.perf_counter()
        total = len(records)

        # Construct only enough cards to populate the initial viewport. This is
        # the only blocking portion of a large rebuild.
        first_count = min(_FIRST_BATCH, total)
        for index in range(first_count):
            _append_livery_card(self, records[index])

        self._relayout_livery_grid(self.livery_search.text())
        record_metric(
            "livery_list_first_paint",
            (time.perf_counter() - started) * 1000.0,
            first_batch=first_count,
            total_count=total,
        )

        if first_count >= total:
            self._fh6_livery_grid_building = False
            record_metric(
                "livery_list_rebuild_complete",
                (time.perf_counter() - started) * 1000.0,
                card_count=first_count,
                expected_count=total,
                incremental=False,
            )
            return

        QTimer.singleShot(
            0,
            lambda: _continue_livery_grid(
                self,
                generation,
                source_result,
                records,
                first_count,
                started,
                0,
            ),
        )

    def _populate_livery_table(self) -> None:
        """Start the visible card-grid rebuild and return after first paint."""
        started = time.perf_counter()
        table = getattr(self, "livery_table", None)
        if table is not None and table.rowCount():
            table.setRowCount(0)
        self._populate_livery_grid()
        record_metric(
            "livery_list_rebuild_blocking",
            (time.perf_counter() - started) * 1000.0,
            first_paint_cards=len(getattr(self, "_livery_grid_cards", ())),
            hidden_table_rows=0,
        )

    def _apply_pointing_cursors(self, root) -> None:
        # _make_saved_content_card() already applies cursors to every newly
        # created card. Scanning the entire livery_grid_host again after all
        # cards are created duplicates that QObject traversal.
        if root is getattr(self, "livery_grid_host", None):
            return
        return original_apply_pointing_cursors(self, root)

    def _scan_finished(self, result) -> None:
        _invalidate_livery_lookup_caches(self)
        return original_scan_finished(self, result)

    MainWindow._invalidate_livery_lookup_caches = _invalidate_livery_lookup_caches
    MainWindow._record_for_content_key = _record_for_content_key
    MainWindow._duplicate_livery_hashes = _duplicate_livery_hashes
    MainWindow._populate_livery_grid = _populate_livery_grid
    MainWindow._populate_livery_table = _populate_livery_table
    MainWindow._apply_pointing_cursors = _apply_pointing_cursors
    MainWindow._scan_finished = _scan_finished
    MainWindow._fh6_livery_list_rebuild_performance_patch_applied = True
    _APPLIED = True
