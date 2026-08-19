from __future__ import annotations

import time
from collections import Counter, deque

from PySide6.QtCore import QTimer

from .performance_metrics import record_metric
from .i18n import tr


_APPLIED = False
_FIRST_BATCH = 8
_INCREMENTAL_BATCH = 8
_RELAYOUT_EVERY = 32
_BATCH_BUDGET_MS = 18.0
_INCREMENTAL_DELAY_MS = 4
_THUMBNAIL_BATCH = 1
_THUMBNAIL_DELAY_MS = 6


def apply_livery_list_rebuild_performance_patch(MainWindow) -> None:
    """Keep large livery libraries responsive while rebuilding the card grid.

    The visible grid is built incrementally, duplicate hashes are calculated
    only when the duplicate filter is actually selected, and thumbnail decode
    is queued one image at a time so WebP work cannot monopolize the GUI thread.
    """
    global _APPLIED
    if _APPLIED:
        return

    original_scan_finished = MainWindow._scan_finished
    original_apply_pointing_cursors = MainWindow._apply_pointing_cursors
    original_load_thumbnail = MainWindow._load_livery_card_thumbnail
    original_unload_thumbnail = MainWindow._unload_livery_card_thumbnail

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

        # Missing full-file hashes are not a startup concern. Request them only
        # when the duplicate filter itself is active. The startup performance
        # patch will wait until card/thumbnail work is idle before reading files.
        try:
            duplicate_active = 9 in self.livery_check_filter.selected_modes()
        except Exception:
            duplicate_active = False
        if duplicate_active:
            missing_hashes = any(
                record.livery_path is not None and not record.content_sha256
                for record in self._custom_liveries()
            )
            if missing_hashes:
                request = getattr(self, "_fh6_request_livery_hash_enrichment", None)
                if callable(request):
                    request()

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

        if since_layout >= _RELAYOUT_EVERY:
            self._relayout_livery_grid(self.livery_search.text())
            since_layout = 0

        # A small non-zero delay gives paint, input and one-thumbnail decode
        # events a chance to run between batches instead of chaining 0-ms timers.
        QTimer.singleShot(
            _INCREMENTAL_DELAY_MS,
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
            _INCREMENTAL_DELAY_MS,
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

    def _drain_thumbnail_queue(self) -> None:
        queue = getattr(self, "_fh6_thumbnail_queue", None)
        if not queue:
            self._fh6_thumbnail_queue_busy = False
            return

        self._fh6_thumbnail_queue_busy = True
        batch_started = time.perf_counter()
        decoded = 0
        while queue and decoded < _THUMBNAIL_BATCH:
            card = queue.popleft()
            try:
                if not getattr(card, "_fh6_thumbnail_pending", False):
                    continue
                card._fh6_thumbnail_pending = False
                if not card.isVisible():
                    continue
                original_load_thumbnail(self, card)
                decoded += 1
            except RuntimeError:
                # Qt object may have been deleted by a refresh while queued.
                continue

        record_metric(
            "thumbnail_decode_batch",
            (time.perf_counter() - batch_started) * 1000.0,
            decoded=decoded,
            remaining=len(queue),
        )

        if queue:
            QTimer.singleShot(_THUMBNAIL_DELAY_MS, lambda: _drain_thumbnail_queue(self))
        else:
            self._fh6_thumbnail_queue_busy = False

    def _queue_thumbnail_load(self, card) -> None:
        try:
            if getattr(card, "_fh6_thumbnail_loaded", False) or getattr(card, "_fh6_thumbnail_pending", False):
                return
            card._fh6_thumbnail_pending = True
        except RuntimeError:
            return

        queue = getattr(self, "_fh6_thumbnail_queue", None)
        if queue is None:
            queue = deque()
            self._fh6_thumbnail_queue = queue
        queue.append(card)

        if not getattr(self, "_fh6_thumbnail_queue_busy", False):
            self._fh6_thumbnail_queue_busy = True
            QTimer.singleShot(0, lambda: _drain_thumbnail_queue(self))

    def _queued_unload_thumbnail(self, card) -> None:
        try:
            card._fh6_thumbnail_pending = False
            original_unload_thumbnail(self, card)
        except RuntimeError:
            return

    def _apply_pointing_cursors(self, root) -> None:
        if root is getattr(self, "livery_grid_host", None):
            return
        return original_apply_pointing_cursors(self, root)

    def _scan_finished(self, result) -> None:
        _invalidate_livery_lookup_caches(self)
        # Invalidate queued thumbnail work from an earlier scan. Stale cards are
        # also protected by the per-card pending flag and RuntimeError guard.
        self._fh6_thumbnail_queue = deque()
        self._fh6_thumbnail_queue_busy = False
        return original_scan_finished(self, result)

    MainWindow._invalidate_livery_lookup_caches = _invalidate_livery_lookup_caches
    MainWindow._record_for_content_key = _record_for_content_key
    MainWindow._duplicate_livery_hashes = _duplicate_livery_hashes
    MainWindow._populate_livery_grid = _populate_livery_grid
    MainWindow._populate_livery_table = _populate_livery_table
    MainWindow._load_livery_card_thumbnail = _queue_thumbnail_load
    MainWindow._unload_livery_card_thumbnail = _queued_unload_thumbnail
    MainWindow._drain_thumbnail_queue = _drain_thumbnail_queue
    MainWindow._apply_pointing_cursors = _apply_pointing_cursors
    MainWindow._scan_finished = _scan_finished
    MainWindow._fh6_livery_list_rebuild_performance_patch_applied = True
    _APPLIED = True
