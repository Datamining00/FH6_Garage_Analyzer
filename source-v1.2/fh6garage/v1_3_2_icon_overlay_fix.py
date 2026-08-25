"""Compatibility exports for the integrated card and busy-overlay visuals."""

from .card_visuals import (
    CARD_ACTION_BUTTON_SIZE,
    CARD_ACTION_ICON_SIZE,
    CARD_ACTION_RADIUS,
    _fix_busy_overlay,
    _normalize_card_actions,
)


def apply_v1_3_2_icon_overlay_fix(MainWindow) -> None:
    MainWindow._fh6_v132_icon_overlay_integrated = True


__all__ = [
    "CARD_ACTION_BUTTON_SIZE",
    "CARD_ACTION_ICON_SIZE",
    "CARD_ACTION_RADIUS",
    "_fix_busy_overlay",
    "_normalize_card_actions",
    "apply_v1_3_2_icon_overlay_fix",
]
