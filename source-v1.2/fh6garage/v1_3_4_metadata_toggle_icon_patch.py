from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QToolButton

from . import v1_3_4_card_features_patch as _features
from .card_icons import icon as card_icon


_ICON_SIZE = 20
_ICON_COLOR = "#5f39d8"


def apply_v1_3_4_metadata_toggle_icon_patch(MainWindow: Any) -> None:
    """Render the metadata collapse control with packaged 20 px PNG assets."""
    if getattr(MainWindow, "_fh6_v134_metadata_toggle_icon_patched", False):
        return

    original_apply = _features._apply_metadata_state

    def apply_metadata_state(card: Any, collapsed: bool) -> None:
        original_apply(card, collapsed)
        toggle = getattr(card, "_fh6_v134_metadata_toggle", None)
        if not isinstance(toggle, QToolButton):
            return
        kind = "expand_left" if collapsed else "collapse_right"
        toggle.setIcon(card_icon(kind, _ICON_COLOR, _ICON_SIZE))
        toggle.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        # Keep the existing text value as an accessibility/fallback state marker,
        # while the visible control is always the packaged PNG icon.
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    _features._apply_metadata_state = apply_metadata_state
    MainWindow._fh6_v134_metadata_toggle_icon_patched = True
