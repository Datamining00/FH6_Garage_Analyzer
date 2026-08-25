from __future__ import annotations

from typing import Any

from .i18n import tr


def _card_for(owner: Any, content_type: str, key: str) -> Any:
    cards = (
        owner._livery_card_by_key
        if content_type == "livery"
        else owner._tuning_card_by_key
    )
    return cards.get(key)


def handle_check_clicked(
    owner: Any,
    content_type: str,
    key: str,
    checked: bool,
) -> None:
    owner.annotations.set_checked(key, checked)
    owner._sync_saved_content_annotation(content_type, key)
    card = _card_for(owner, content_type, key)
    if card is not None:
        checkbox = getattr(card, "_fh6_check_box", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)
        card.setProperty("checked", checked)
    owner._refresh_after_annotation_change(
        content_type,
        filter_modes={1, 10},
    )


def handle_triangle_clicked(
    owner: Any,
    content_type: str,
    key: str,
    enabled: bool,
) -> None:
    owner.annotations.set_triangle(key, enabled)
    owner._sync_saved_content_annotation(content_type, key)
    card = _card_for(owner, content_type, key)
    if card is not None:
        triangle_box = getattr(card, "_fh6_triangle_box", None)
        if triangle_box is not None:
            triangle_box.blockSignals(True)
            triangle_box.setChecked(enabled)
            triangle_box.blockSignals(False)
        card.setProperty("triangle", enabled)
    owner._refresh_after_annotation_change(
        content_type,
        filter_modes={5, 10},
    )


def handle_excluded_clicked(
    owner: Any,
    content_type: str,
    key: str,
    enabled: bool,
) -> None:
    owner.annotations.set_excluded(key, enabled)
    owner._sync_saved_content_annotation(content_type, key)
    card = _card_for(owner, content_type, key)
    if card is not None:
        excluded_box = getattr(card, "_fh6_excluded_box", None)
        if excluded_box is not None:
            excluded_box.blockSignals(True)
            excluded_box.setChecked(enabled)
            excluded_box.blockSignals(False)
        card.setProperty("excluded", enabled)
    owner._refresh_after_annotation_change(
        content_type,
        filter_modes={7, 10},
    )


def handle_memo_clicked(owner: Any, content_type: str, key: str) -> None:
    current = owner.annotations.get(key).note
    note = owner._edit_content_note_dialog(current, content_type, key)
    if note is None:
        return

    owner.annotations.set_note(key, note)
    owner._sync_saved_content_annotation(content_type, key)
    card = _card_for(owner, content_type, key)
    if card is not None:
        owner._refresh_card_search_text(card, key)
        memo_button = getattr(card, "_fh6_memo_button", None)
        if memo_button is not None:
            clean_note = (note or "").strip()
            memo_button.setIcon(owner._detail_memo_icon(bool(clean_note)))
            memo_button.setToolTip(
                clean_note + tr("memo.edit_suffix")
                if clean_note
                else tr("memo.none_add")
            )

    owner._show_status(tr("memo.saved"), 1800)
    owner._refresh_after_annotation_change(
        content_type,
        filter_modes={3, 4},
        search_sensitive=True,
    )
