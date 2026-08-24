from __future__ import annotations

from .refresh_history import process_livery_refresh


def apply_v1_3_2_refresh_diff_patch(MainWindow) -> None:
    """Capture refresh-to-refresh livery changes with read-only thumbnail history."""
    if getattr(MainWindow, "_fh6_v132_refresh_diff_patched", False):
        return

    original_populate_all = MainWindow._populate_all

    def patched_populate_all(self) -> None:
        result = getattr(self, "result", None)
        if result is not None:
            try:
                diff = process_livery_refresh(result)
                self._fh6_latest_livery_diff = diff
                self._fh6_latest_livery_diff_summary = {
                    "baseline": diff.baseline,
                    "added": len(diff.added),
                    "removed": len(diff.removed),
                    "changed": len(diff.changed),
                }
                self._fh6_latest_livery_diff_error = ""
            except Exception as exc:
                # Refresh history is auxiliary.  A cache/disk failure must never
                # prevent the FH6 save itself from loading.
                self._fh6_latest_livery_diff = None
                self._fh6_latest_livery_diff_summary = None
                self._fh6_latest_livery_diff_error = str(exc)

        original_populate_all(self)

    MainWindow._populate_all = patched_populate_all
    MainWindow._fh6_v132_refresh_diff_patched = True
