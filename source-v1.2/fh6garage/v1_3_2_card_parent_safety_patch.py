from __future__ import annotations

from typing import Any


def apply_v1_3_2_card_parent_safety_patch(MainWindow) -> None:
    """Parent saved-content cards before any later visual reparent/show work.

    The v1.3.2 list fix relies on a strict Windows invariant: newly created
    card QFrames must not remain parentless across an event-loop turn. The
    card-action rail patch reparents and shows several child QToolButtons while
    restructuring the thumbnail area, so this safety layer runs immediately
    before that rail patch and guarantees that the card is already owned by the
    correct grid host and explicitly hidden first.

    If the grid already has a settled card width (for example while deferred
    auction cards are appended after the first paint), apply that width before
    later visual patches run. This prevents a newly appended card from briefly
    taking the full viewport width before the next grid-width synchronization.

    The normal performance/list code may call setParent()/hide() again after
    _make_saved_content_card() returns; those repeated calls are harmless.
    """
    if getattr(MainWindow, "_fh6_v132_card_parent_safety_patched", False):
        return

    original_make_card = MainWindow._make_saved_content_card

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)

        host = None
        if content_type == "livery":
            host = getattr(self, "livery_grid_host", None)
        elif content_type == "tuning":
            host = getattr(self, "tuning_grid_host", None)

        if host is not None:
            card.setParent(host)
            card.hide()
            card.setProperty("fh6ParentSafeBeforeRails", True)

            settled_width = getattr(
                self,
                f"_fh6_v131_{content_type}_card_width",
                None,
            )
            if isinstance(settled_width, int) and settled_width > 1:
                card.setFixedWidth(settled_width)
                card.setProperty("fh6InheritedSettledCardWidth", settled_width)

        return card

    MainWindow._make_saved_content_card = patched_make_card
    MainWindow._fh6_v132_card_parent_safety_patched = True
