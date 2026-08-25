from __future__ import annotations

from .refresh_history import process_livery_refresh


def update_livery_refresh_diff(owner) -> None:
    """Capture refresh changes without allowing history failures to block loading."""
    result = getattr(owner, "result", None)
    if result is None:
        return
    try:
        yield_hook = getattr(owner, "_keep_busy_responsive", None)
        diff = process_livery_refresh(
            result,
            yield_hook=yield_hook if callable(yield_hook) else None,
        )
        owner._fh6_latest_livery_diff = diff
        owner._fh6_latest_livery_diff_summary = {
            "baseline": diff.baseline,
            "added": len(diff.added),
            "removed": len(diff.removed),
            "changed": len(diff.changed),
        }
        owner._fh6_latest_livery_diff_error = ""
    except Exception as exc:
        # Refresh history is auxiliary. A cache/disk failure must never prevent
        # the FH6 save itself from loading.
        owner._fh6_latest_livery_diff = None
        owner._fh6_latest_livery_diff_summary = None
        owner._fh6_latest_livery_diff_error = str(exc)
