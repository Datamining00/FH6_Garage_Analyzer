from __future__ import annotations

from typing import Any

from .creator_alias_views import normalize_card_alias_properties
from .models import LiveryRecord
from .saved_content_presenter import search_matches
from .ui_responsiveness import (
    _livery_visibility_allowed,
    _schedule_grid_followup,
    _yield_busy_events,
)


def relayout_saved_content(
    owner: Any,
    content_type: str,
    text: str = "",
) -> None:
    cards = getattr(owner, f"_{content_type}_grid_cards")
    host = getattr(owner, f"{content_type}_grid_host")
    layout = getattr(owner, f"{content_type}_grid_layout")

    for card in cards:
        normalize_card_alias_properties(owner, content_type, card)
    host.setUpdatesEnabled(False)
    if content_type == "livery":
        owner._clear_livery_grid_layout()
        duplicate_hashes = owner._duplicate_livery_hashes()
    else:
        owner._clear_tuning_grid_layout()
        duplicate_hashes = set()

    visible_cards = []
    for index, card in enumerate(cards):
        haystack = str(card.property("searchText") or "")
        checked = bool(card.property("checked"))
        triangle = bool(card.property("triangle"))
        excluded = bool(card.property("excluded"))
        key = str(card.property("annotationKey") or "")
        note = owner.annotations.get(key).note if key else ""

        if content_type == "livery":
            record = (
                owner._record_for_content_key("livery", key)
                if key
                else None
            )
            duplicate = bool(
                isinstance(record, LiveryRecord)
                and record.content_sha256
                and record.content_sha256 in duplicate_hashes
            )
            matched = search_matches(
                haystack,
                text,
            ) and owner._livery_filter_matches(
                checked,
                note,
                triangle,
                excluded,
                duplicate,
            )
            if matched and not _livery_visibility_allowed(owner, card):
                matched = False
        else:
            matched = search_matches(
                haystack,
                text,
            ) and owner._saved_content_filter_matches(
                "tuning",
                checked,
                note,
                triangle,
                excluded,
            )

        if matched:
            visible_cards.append(card)
        else:
            owner._unload_livery_card_thumbnail(card)
        _yield_busy_events(owner, force=(index == 0))

    owner._layout_visible_grid_cards(content_type, visible_cards)
    layout.activate()
    host.setUpdatesEnabled(True)
    host.update()

    if content_type == "livery":
        owner._sync_livery_grid_card_widths()
    else:
        owner._sync_tuning_grid_card_widths()
    _schedule_grid_followup(owner, content_type)
