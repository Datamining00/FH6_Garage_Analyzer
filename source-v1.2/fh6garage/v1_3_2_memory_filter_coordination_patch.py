from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QPushButton


FILTER_DEFAULT = "DEFAULT"
LEGACY_AUCTION_STATE_MODES = (12, 13)


def _clear_legacy_auction_state_filter(window: Any) -> None:
    if getattr(window, "_fh6_memory_livery_filter_mode", FILTER_DEFAULT) == FILTER_DEFAULT:
        return
    filter_button = getattr(window, "livery_check_filter", None)
    actions = getattr(filter_button, "_actions", {}) if filter_button is not None else {}
    if not isinstance(actions, dict):
        return
    changed = False
    for mode in LEGACY_AUCTION_STATE_MODES:
        action = actions.get(mode)
        if action is not None and action.isChecked():
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
            changed = True
    if changed:
        search = getattr(window, "livery_search", None)
        if search is not None:
            window._filter_saved_content_views("livery", search.text())


def _legacy_filter_changed(window: Any) -> None:
    filter_button = getattr(window, "livery_check_filter", None)
    if filter_button is None:
        return
    selected = filter_button.selected_modes()
    if not any(mode in selected for mode in LEGACY_AUCTION_STATE_MODES):
        return

    window._fh6_memory_livery_filter_mode = FILTER_DEFAULT
    for name in ("livery_applied_toggle", "livery_unapplied_toggle"):
        button = getattr(window, name, None)
        if isinstance(button, QPushButton) and button.isChecked():
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)


def apply_v1_3_2_memory_filter_coordination_patch(MainWindow: Any) -> None:
    """Keep legacy auction-state and new all-livery state selectors non-conflicting."""
    if getattr(MainWindow, "_fh6_v132_memory_filter_coordination_patched", False):
        return

    original_init = MainWindow.__init__

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        for name in ("livery_applied_toggle", "livery_unapplied_toggle"):
            button = getattr(self, name, None)
            if isinstance(button, QPushButton):
                button.clicked.connect(
                    lambda _checked=False, owner=self:
                    _clear_legacy_auction_state_filter(owner)
                )
        filter_button = getattr(self, "livery_check_filter", None)
        if filter_button is not None:
            filter_button.selectionChanged.connect(
                lambda owner=self: _legacy_filter_changed(owner)
            )

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v132_memory_filter_coordination_patched = True
