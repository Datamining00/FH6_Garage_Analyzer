from __future__ import annotations

import re
from typing import Any

from PySide6.QtWidgets import QPushButton

from . import v1_3_2_memory_state_patch as _memory_state
from .memory_applied_state import MemoryScanResult, normalized_livery_name
from .models import LiveryRecord


FILTER_DEFAULT = "DEFAULT"
LEGACY_AUCTION_STATE_MODES = (12, 13)
_NORMALIZED_LIVERY_NAME_RE = re.compile(r"^Livery_\d+_\d{14}$")


def _classify_soulbound_from_memory(
    window: Any,
    result: MemoryScanResult,
) -> tuple[set[str], set[str], set[str]]:
    """Use the trusted exact memory identity as the primary SoulBound state.

    CacheThumbnails/manifest data is auxiliary evidence only. Missing, stale, or
    ambiguous cache metadata must not turn a conclusive HIGH/MEDIUM memory
    snapshot into REVIEW.
    """
    records = [
        record
        for record in getattr(getattr(window, "result", None), "liveries", [])
        if isinstance(record, LiveryRecord) and record.kind == "SoulBoundLivery"
    ]

    applied: set[str] = set()
    unapplied: set[str] = set()
    review: set[str] = set()

    for record in records:
        name = normalized_livery_name(record.container_name)
        if not name or _NORMALIZED_LIVERY_NAME_RE.fullmatch(name) is None:
            review.add(str(record.container_name or "<unknown>"))
            continue
        if name in result.active_livery_names:
            applied.add(name)
        else:
            unapplied.add(name)

    return applied, unapplied, review


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

    # v1.3.3 Beta: exact memory membership is authoritative for SoulBound
    # applied/unapplied state. Cache/manifest evidence remains auxiliary only.
    _memory_state._classify_soulbound = _classify_soulbound_from_memory

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
