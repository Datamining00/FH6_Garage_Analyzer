from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QWidget

from .i18n import get_language, tr


def _txt(ko: str, en: str) -> str:
    return ko if get_language() == "ko" else en


def creator_display(window: Any, raw_name: str) -> str:
    raw = (raw_name or "").strip()
    if not raw:
        return tr("creator.none")
    return window.creator_aliases.display_name(raw)


def decorate_creator_copy_label(window: Any, card: QWidget, raw_creator: str) -> None:
    display = creator_display(window, raw_creator)
    prefix = tr("card.creator_label")
    for label in card.findChildren(QLabel):
        if getattr(label, "prefix", None) != prefix:
            continue
        setter = getattr(label, "setCopyValue", None)
        if callable(setter):
            setter(display)
        else:
            label.setText(f"{prefix}: {display}")
        for controller in getattr(card, "_fh6_metadata_elide_controllers", []):
            if getattr(controller, "label", None) is label:
                schedule = getattr(controller, "schedule", None)
                if callable(schedule):
                    schedule()
        break


def normalize_card_alias_properties(window: Any, content_type: str, card: QWidget) -> None:
    key = str(card.property("annotationKey") or "")
    if not key:
        return
    record = window._record_for_content_key(content_type, key)
    if record is None:
        return

    raw = (record.header.creator or "").strip()
    current_search = str(card.property("searchText") or "")
    last_augmented = getattr(card, "_fh6_alias_last_search", None)
    if last_augmented is None or current_search != last_augmented:
        card._fh6_alias_base_search = current_search
    base_search = str(getattr(card, "_fh6_alias_base_search", current_search))

    if raw:
        group = window.creator_aliases.group_for(raw)
        display = window.creator_aliases.display_name(raw)
        augmented = " ".join(
            piece for piece in (base_search, display, *group.all_names()) if piece
        ).casefold()
        card.setProperty("creatorGroupKey", f"creator:{group.current.casefold()}")
        card.setProperty("creatorGroupLabel", display)
    else:
        augmented = base_search.casefold()
        card.setProperty("creatorGroupKey", "creator:")
        card.setProperty("creatorGroupLabel", tr("creator.none"))

    card.setProperty("searchText", augmented)
    card._fh6_alias_last_search = augmented


def observed_creator_names(window: Any) -> list[str]:
    names: dict[str, str] = {}
    result = getattr(window, "result", None)
    if result is not None:
        for record in [*result.liveries, *result.tunings]:
            name = (record.header.creator or "").strip()
            if name:
                names.setdefault(name.casefold(), name)
    for group in window.creator_aliases.groups:
        for name in group.all_names():
            if name:
                names.setdefault(name.casefold(), name)
    return sorted(names.values(), key=str.casefold)


def refresh_alias_views(window: Any) -> None:
    reset_cards = getattr(window, "_fh6_v132_reset_ui_card_cache", None)
    if callable(reset_cards):
        reset_cards()
    if getattr(window, "result", None) is None:
        return
    window._populate_creator_table()
    window._populate_livery_table()
    window._populate_tuning_table()
    window._filter_dashboard_table(window.car_search.text())
    if window.dashboard_content_stack.currentIndex() == 1:
        window._update_selected_creator()


def open_alias_dialog(window: Any) -> None:
    from .creator_alias_dialog import open_creator_alias_dialog

    open_creator_alias_dialog(window)


def initialize_creator_alias_ui(window: Any) -> None:
    sidebar = window.findChild(QFrame, "sidebar")
    if sidebar is None or sidebar.layout() is None:
        return
    button = QPushButton(_txt("제작자 이름 관리", "Creator aliases"), sidebar)
    button.setObjectName("creatorAliasManagerButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        "QPushButton { color:#c7c9d4;background:transparent;border:0;"
        "padding:8px 10px;text-align:left;border-radius:8px; }"
        "QPushButton:hover { background:#242632;color:white; }"
    )
    button.clicked.connect(lambda: open_alias_dialog(window))
    sidebar.layout().insertWidget(1 + len(getattr(window, "nav_buttons", [])), button)
    window.creator_alias_button = button
