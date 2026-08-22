from __future__ import annotations

from collections import Counter

from .models import LiveryRecord


def apply_v1_3_2_list_fixes(MainWindow) -> None:
    """Keep the v1.3.1 livery construction path while avoiding SoulBound duplication.

    The v1.3.1 UI maintains a hidden QTableWidget and a visible card grid for
    liveries. v1.3.2 originally fed SoulBound records through both structures,
    even though the table is not shown in the current grid-only UI. Keep that
    hidden table My-Designs-only and add auction records only to the visible
    grid. Card construction itself remains the original synchronous v1.3.1
    path.

    The original filtering code also resolves each card key by scanning the
    complete livery list and rebuilds the duplicate hash set for every row/card.
    Cache those pure lookups per ScanResult without changing their semantics.
    """
    if getattr(MainWindow, "_fh6_v132_list_fix_patched", False):
        return

    original_scan_finished = MainWindow._scan_finished
    original_sorted_saved_content = MainWindow._sorted_saved_content
    original_populate_saved_content_table = MainWindow._populate_saved_content_table
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
        if (
            content_type == "livery"
            and getattr(self, "_fh6_v132_building_hidden_livery_table", False)
        ):
            # The table is hidden in the grid-only UI. Preserve the exact
            # v1.3.1 content scope here: saved My Designs only.
            return list(self._custom_liveries())
        return original_sorted_saved_content(self, content_type)

    def patched_populate_saved_content_table(self, content_type: str) -> None:
        if content_type != "livery":
            original_populate_saved_content_table(self, content_type)
            return

        self._fh6_v132_building_hidden_livery_table = True
        try:
            original_populate_saved_content_table(self, content_type)
        finally:
            self._fh6_v132_building_hidden_livery_table = False

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

    MainWindow._scan_finished = patched_scan_finished
    MainWindow._sorted_saved_content = patched_sorted_saved_content
    MainWindow._populate_saved_content_table = patched_populate_saved_content_table
    MainWindow._record_for_content_key = patched_record_for_content_key
    MainWindow._duplicate_livery_hashes = patched_duplicate_livery_hashes
    MainWindow._fh6_v132_list_fix_patched = True
