from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QToolButton

from .i18n import tr


def _cached_card(window: Any, content_type: str, key: str):
    mapping = (
        getattr(window, "_livery_card_by_key", {})
        if content_type == "livery"
        else getattr(window, "_tuning_card_by_key", {})
    )
    return mapping.get(key) if isinstance(mapping, dict) else None


def _set_checked_silently(button: Any, value: bool) -> None:
    if not isinstance(button, QToolButton):
        return
    old = button.blockSignals(True)
    try:
        button.setChecked(bool(value))
    finally:
        button.blockSignals(old)


def _sync_cached_annotation_card(window: Any, content_type: str, key: str) -> None:
    card = _cached_card(window, content_type, key)
    if card is None:
        return
    annotation = window.annotations.get(key)
    for attr, prop, value in (
        ("_fh6_check_box", "checked", annotation.checked),
        ("_fh6_triangle_box", "triangle", annotation.triangle),
        ("_fh6_excluded_box", "excluded", annotation.excluded),
    ):
        _set_checked_silently(getattr(card, attr, None), bool(value))
        card.setProperty(prop, bool(value))

    memo = getattr(card, "_fh6_memo_button", None)
    if isinstance(memo, QToolButton):
        note = (annotation.note or "").strip()
        memo.setIcon(window._detail_memo_icon(bool(note)))
        memo.setToolTip((note + tr("memo.edit_suffix")) if note else tr("memo.none_add"))


def _sync_cached_hidden_card(window: Any, key: str, hidden: bool) -> None:
    card = _cached_card(window, "livery", key)
    if card is None:
        return
    _set_checked_silently(getattr(card, "_fh6_hide_button", None), bool(hidden))


def _refresh_dialog_memo_button(window: Any, card: Any, key: str) -> None:
    memo = getattr(card, "_fh6_memo_button", None)
    if not isinstance(memo, QToolButton):
        return
    annotation = window.annotations.get(key)
    note = (annotation.note or "").strip()
    memo.setIcon(window._detail_memo_icon(bool(note)))
    memo.setToolTip((note + tr("memo.edit_suffix")) if note else tr("memo.none_add"))
