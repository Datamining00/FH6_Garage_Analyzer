"""Compatibility exports for the retired v1.3.2 UI performance patch."""

from .saved_content_cards import (
    _delete_cached_cards,
    _ensure_scan_generation,
    _populate_livery_grid_reusing_cards,
    _populate_tuning_grid_reusing_cards,
    initialize_ui_performance_state,
)


def apply_v1_3_2_ui_performance_patches(MainWindow) -> None:
    """Retained as an idempotent no-op for older external imports."""

    MainWindow._fh6_v132_ui_performance_integrated = True


__all__ = [
    "_delete_cached_cards",
    "_ensure_scan_generation",
    "_populate_livery_grid_reusing_cards",
    "_populate_tuning_grid_reusing_cards",
    "apply_v1_3_2_ui_performance_patches",
    "initialize_ui_performance_state",
]
