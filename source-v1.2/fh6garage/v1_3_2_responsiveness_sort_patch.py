"""Compatibility exports for integrated UI responsiveness behavior."""

from .ui_responsiveness import (
    _AUCTION_APPLIED_MODE,
    _AUCTION_UNAPPLIED_MODE,
    _BUSY_YIELD_INTERVAL_SECONDS,
    _HIDDEN_MODE,
    _install_download_sort_default,
    _livery_visibility_allowed,
    _responsive_clear_grid_layout,
    _schedule_grid_followup,
    _yield_busy_events,
)


def apply_v1_3_2_responsiveness_sort_patch(MainWindow) -> None:
    MainWindow._fh6_v132_responsiveness_integrated = True


__all__ = [
    "_AUCTION_APPLIED_MODE",
    "_AUCTION_UNAPPLIED_MODE",
    "_BUSY_YIELD_INTERVAL_SECONDS",
    "_HIDDEN_MODE",
    "_install_download_sort_default",
    "_livery_visibility_allowed",
    "_responsive_clear_grid_layout",
    "_schedule_grid_followup",
    "_yield_busy_events",
    "apply_v1_3_2_responsiveness_sort_patch",
]
