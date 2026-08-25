"""Compatibility exports for the integrated compact card layout."""

from .card_metadata_layout import (
    CONTENT_HORIZONTAL_MARGIN,
    GRID_HORIZONTAL_SPACING,
    GRID_SIDE_MARGIN,
    SIDEBAR_HORIZONTAL_MARGIN,
    SIDEBAR_WIDTH,
    _compact_window_chrome,
    _configure_card_metadata,
    _ElidedCopyValueController,
)


def apply_v1_3_2_compact_card_layout_patch(MainWindow) -> None:
    """Retained as an idempotent no-op for older external imports."""

    MainWindow._fh6_v132_compact_card_layout_integrated = True


__all__ = [
    "CONTENT_HORIZONTAL_MARGIN",
    "GRID_HORIZONTAL_SPACING",
    "GRID_SIDE_MARGIN",
    "SIDEBAR_HORIZONTAL_MARGIN",
    "SIDEBAR_WIDTH",
    "_ElidedCopyValueController",
    "_compact_window_chrome",
    "_configure_card_metadata",
    "apply_v1_3_2_compact_card_layout_patch",
]
