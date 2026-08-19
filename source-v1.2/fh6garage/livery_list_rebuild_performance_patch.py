from __future__ import annotations

import time
from collections import Counter

from .performance_metrics import record_metric


_APPLIED = False


def apply_livery_list_rebuild_performance_patch(MainWindow) -> None:
    """Remove quadratic and hidden-widget work from the tile-only livery view.

    The visible livery UI is the card grid. The legacy QTableWidget is kept only
    as an inert compatibility object, so rebuilding hundreds of hidden rows is
    wasted work. The original relayout also performed two O(n) searches per
    card: annotation-key -> record lookup and duplicate-hash recomputation.
    Both are cached once per scan instead.
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

    def _populate_livery_table(self) -> None:
        """Rebuild only the visible card grid.

        _populate_livery_grid() already performs the final relayout using the
        current search/filter state. Calling _filter_livery_views() immediately
        afterwards used to relayout the same grid a second time and also filter
        the permanently hidden legacy table.
        """
        started = time.perf_counter()
        table = getattr(self, "livery_table", None)
        if table is not None and table.rowCount():
            table.setRowCount(0)
        self._populate_livery_grid()
        record_metric(
            "livery_list_rebuild",
            (time.perf_counter() - started) * 1000.0,
            card_count=len(getattr(self, "_livery_grid_cards", ())),
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
    MainWindow._populate_livery_table = _populate_livery_table
    MainWindow._apply_pointing_cursors = _apply_pointing_cursors
    MainWindow._scan_finished = _scan_finished
    MainWindow._fh6_livery_list_rebuild_performance_patch_applied = True
    _APPLIED = True
