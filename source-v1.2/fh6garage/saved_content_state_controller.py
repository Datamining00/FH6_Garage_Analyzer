from __future__ import annotations

from typing import Any

from .i18n import tr


def set_grouping(
    owner: Any,
    content_type: str,
    enabled: bool,
    *,
    group_kind: str,
) -> None:
    preference_suffix = (
        "group_by_vehicle" if group_kind == "vehicle" else "group_by_creator"
    )
    other_suffix = (
        "creator_group_button" if group_kind == "vehicle" else "group_button"
    )
    other_preference_suffix = (
        "group_by_creator" if group_kind == "vehicle" else "group_by_vehicle"
    )
    owner.local_preferences.set_bool(
        f"{content_type}_{preference_suffix}",
        enabled,
    )
    if enabled:
        other = getattr(owner, f"{content_type}_{other_suffix}", None)
        if other is not None and other.isChecked():
            other.blockSignals(True)
            other.setChecked(False)
            other.blockSignals(False)
            owner.local_preferences.set_bool(
                f"{content_type}_{other_preference_suffix}",
                False,
            )

    search = (
        owner.livery_search
        if content_type == "livery"
        else owner.tuning_search
    )
    if owner.result is None:
        return
    noun = (
        tr("content.noun_livery")
        if content_type == "livery"
        else tr("content.noun_tuning")
    )
    message_key = (
        f"content.grouping_{group_kind}" if enabled else "content.relayout"
    )
    text = search.text()
    owner._view_operations.request(
        content_type,
        tr(message_key, noun=noun),
        lambda: owner._filter_saved_content_views(
            content_type,
            text,
            preserve_scroll=True,
        ),
    )


def set_sort_mode(owner: Any, content_type: str, mode: str) -> None:
    if (
        content_type not in {"livery", "tuning"}
        or mode not in {"default", "brand", "creator", "download"}
    ):
        return

    noun = (
        tr("content.noun_livery")
        if content_type == "livery"
        else tr("content.noun_tuning")
    )
    if mode == "download":
        for button_name, preference_name in (
            (
                f"{content_type}_group_button",
                f"{content_type}_group_by_vehicle",
            ),
            (
                f"{content_type}_creator_group_button",
                f"{content_type}_group_by_creator",
            ),
        ):
            group_button = getattr(owner, button_name)
            if group_button.isChecked():
                group_button.blockSignals(True)
                group_button.setChecked(False)
                group_button.blockSignals(False)
                owner.local_preferences.set_bool(preference_name, False)

    mode_attr = (
        "_livery_sort_mode"
        if content_type == "livery"
        else "_tuning_sort_mode"
    )
    descending_attr = (
        "_livery_sort_descending"
        if content_type == "livery"
        else "_tuning_sort_descending"
    )
    previous_mode = getattr(owner, mode_attr)
    previous_descending = bool(getattr(owner, descending_attr))
    next_descending = (
        True
        if mode == "download" and previous_mode != mode
        else not previous_descending
        if previous_mode == mode
        else False
    )
    setattr(owner, descending_attr, next_descending)
    setattr(owner, mode_attr, mode)
    update_sort_button_labels(owner, content_type)

    if owner.result is None:
        return
    populate = (
        owner._populate_livery_view
        if content_type == "livery"
        else owner._populate_tuning_view
    )
    owner._view_operations.request(
        content_type,
        tr("content.sorting", noun=noun),
        populate,
    )


def update_sort_button_labels(owner: Any, content_type: str) -> None:
    buttons = (
        owner.livery_sort_buttons
        if content_type == "livery"
        else owner.tuning_sort_buttons
    )
    mode = (
        owner._livery_sort_mode
        if content_type == "livery"
        else owner._tuning_sort_mode
    )
    descending = (
        owner._livery_sort_descending
        if content_type == "livery"
        else owner._tuning_sort_descending
    )
    labels = {
        "default": tr("content.sort_default"),
        "brand": tr("content.sort_brand"),
        "creator": tr("content.sort_creator"),
        "download": tr("content.sort_download"),
    }
    for key, button in buttons.items():
        arrow = ("↓" if descending else "↑") if key == mode else ""
        button.setText(labels[key] + arrow)
