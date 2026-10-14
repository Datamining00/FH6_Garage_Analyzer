from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
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


def apply_v1_3_2_change_view_alias_sync_patch(MainWindow) -> None:
    """Keep duplicate change-view cards and the main cached card state in lockstep."""
    if getattr(MainWindow, "_fh6_v132_change_view_alias_sync_patched", False):
        return

    original_sync_annotation = MainWindow._sync_saved_content_annotation
    original_make_card = MainWindow._make_saved_content_card
    original_set_hidden = getattr(MainWindow, "_fh6_v132_set_livery_hidden", None)

    def sync_saved_content_annotation(self, content_type: str, key: str) -> None:
        original_sync_annotation(self, content_type, key)
        _sync_cached_annotation_card(self, content_type, key)

    def make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        memo = getattr(card, "_fh6_memo_button", None)
        if isinstance(memo, QToolButton):
            # The original memo slot opens a modal editor. This additional slot
            # runs after that handler returns and refreshes this duplicate card's
            # memo icon from the saved annotation state.
            memo.clicked.connect(
                lambda _checked=False, c=card, k=key:
                QTimer.singleShot(0, lambda: _refresh_dialog_memo_button(self, c, k))
            )
        return card

    MainWindow._sync_saved_content_annotation = sync_saved_content_annotation
    MainWindow._make_saved_content_card = make_card

    if callable(original_set_hidden):
        def set_hidden(self, key: str, hidden: bool) -> None:
            original_set_hidden(self, key, hidden)
            _sync_cached_hidden_card(self, key, hidden)

        MainWindow._fh6_v132_set_livery_hidden = set_hidden

    MainWindow._fh6_v132_change_view_alias_sync_patched = True
