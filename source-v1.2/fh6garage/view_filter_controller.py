from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer

from .i18n import tr


def request_saved_content_filter(
    owner: Any,
    content_type: str,
    text: str,
) -> None:
    if owner.result is None:
        filter_saved_content_views(
            owner,
            content_type,
            text,
            preserve_scroll=True,
        )
        return
    noun = (
        tr("content.noun_livery")
        if content_type == "livery"
        else tr("content.noun_tuning")
    )
    owner._view_operations.request(
        content_type,
        tr("content.filtering", noun=noun),
        lambda: filter_saved_content_views(
            owner,
            content_type,
            text,
            preserve_scroll=True,
        ),
    )


def filter_saved_content_views(
    owner: Any,
    content_type: str,
    text: str,
    *,
    preserve_scroll: bool = False,
) -> None:
    if content_type == "livery":
        owner._filter_livery_views(
            text,
            preserve_scroll=preserve_scroll,
        )
        return
    if content_type != "tuning":
        return

    scrollbar = owner.tuning_grid_scroll.verticalScrollBar()
    old_scroll = scrollbar.value()
    owner._relayout_tuning_grid(text)
    if not preserve_scroll:
        scrollbar.setValue(0)
        return
    restore_grid_scroll(scrollbar, old_scroll)
    QTimer.singleShot(0, owner._schedule_visible_tuning_thumbnails)


def restore_grid_scroll(scrollbar: Any, value: int) -> None:
    def restore() -> None:
        scrollbar.setValue(min(value, scrollbar.maximum()))

    restore()
    QTimer.singleShot(0, restore)
    QTimer.singleShot(30, restore)


def refresh_after_annotation_change(
    owner: Any,
    content_type: str,
    *,
    filter_modes: set[int],
    search_sensitive: bool = False,
) -> None:
    filter_box = (
        owner.livery_check_filter
        if content_type == "livery"
        else owner.tuning_check_filter
    )
    search = (
        owner.livery_search
        if content_type == "livery"
        else owner.tuning_search
    )
    if filter_box.selected_modes().intersection(filter_modes) or (
        search_sensitive and bool(search.text().strip())
    ):
        filter_saved_content_views(
            owner,
            content_type,
            search.text(),
            preserve_scroll=True,
        )
