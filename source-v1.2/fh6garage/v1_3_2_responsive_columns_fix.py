"""Compatibility exports for the integrated responsive grid layout."""

from .saved_content_layout import (
    _current_grid_columns,
    _dynamic_layout_visible_grid_cards,
    _dynamic_sync_grid_card_widths,
)


def apply_v1_3_2_responsive_columns_fix(MainWindow) -> None:
    """Retained as an idempotent no-op for older external imports."""

    MainWindow._fh6_v132_responsive_columns_integrated = True


__all__ = [
    "_current_grid_columns",
    "_dynamic_layout_visible_grid_cards",
    "_dynamic_sync_grid_card_widths",
    "apply_v1_3_2_responsive_columns_fix",
]
