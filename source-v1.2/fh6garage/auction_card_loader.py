from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer

from .models import LiveryRecord


def schedule_auction_cards(owner: Any) -> None:
    """Append auction cards incrementally after synchronous scan painting."""
    generation = getattr(owner, "_fh6_v132_auction_build_generation", 0) + 1
    owner._fh6_v132_auction_build_generation = generation
    owner._fh6_v132_auction_card_errors = []
    if owner.result is None:
        return

    auction_records = [
        record
        for record in owner._sorted_saved_content("livery")
        if isinstance(record, LiveryRecord) and record.kind == "SoulBoundLivery"
    ]
    if not auction_records:
        return

    state = {"index": 0}

    def current() -> bool:
        return generation == getattr(
            owner,
            "_fh6_v132_auction_build_generation",
            generation,
        ) and owner.result is not None

    def finish() -> None:
        if not current():
            return
        ordered_cards = []
        seen: set[str] = set()
        for record in owner._sorted_saved_content("livery"):
            if not isinstance(record, LiveryRecord):
                continue
            key = owner._content_annotation_key("livery", record)
            card = owner._livery_card_by_key.get(key)
            if card is not None and key not in seen:
                ordered_cards.append(card)
                seen.add(key)

        for card in owner._livery_grid_cards:
            key = str(card.property("annotationKey") or "")
            if key and key not in seen:
                ordered_cards.append(card)
                seen.add(key)
        owner._livery_grid_cards[:] = ordered_cards
        owner._filter_livery_views(
            owner.livery_search.text(),
            preserve_scroll=True,
        )
        owner._apply_pointing_cursors(owner.livery_grid_host)

    def append_next() -> None:
        if not current():
            return
        index = state["index"]
        if index >= len(auction_records):
            finish()
            return

        record = auction_records[index]
        state["index"] = index + 1
        card = None
        try:
            key = owner._content_annotation_key("livery", record)
            if key not in owner._livery_card_by_key:
                annotation = owner.annotations.get(key)
                card = owner._make_livery_card(record, key)
                card.setParent(owner.livery_grid_host)
                card.hide()
                card.setProperty(
                    "searchText",
                    owner._livery_search_text(record, annotation.note),
                )
                card.setProperty("annotationKey", key)
                card.setProperty(
                    "vehicleGroupKey",
                    f"id:{record.car_id}" if record.car_id is not None else "unknown",
                )
                card.setProperty(
                    "vehicleGroupLabel",
                    owner._car_label(record.car_id),
                )
                creator_label = (record.header.creator or "").strip() or "—"
                card.setProperty(
                    "creatorGroupKey",
                    f"creator:{creator_label.casefold()}",
                )
                card.setProperty("creatorGroupLabel", creator_label)
                card.setProperty("checked", annotation.checked)
                card.setProperty("triangle", annotation.triangle)
                card.setProperty("excluded", annotation.excluded)
                owner._livery_grid_cards.append(card)
                owner._livery_card_by_key[key] = card
        except Exception as exc:  # noqa: BLE001 - isolate one malformed card
            if card is not None:
                card.hide()
                card.deleteLater()
            owner._fh6_v132_auction_card_errors.append(
                (record.container_name, f"{type(exc).__name__}: {exc}")
            )
        QTimer.singleShot(0, append_next)

    QTimer.singleShot(0, append_next)
