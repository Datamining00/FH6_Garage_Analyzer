from __future__ import annotations

from typing import Any

from .creator_alias_view import sort_by_creator_alias
from .models import LiveryRecord, TuningRecord
from .saved_content_view import SortSpec, sort_records, vehicle_brand_sort_key


def custom_liveries(owner: Any) -> list[LiveryRecord]:
    if not owner.result:
        return []
    return [
        record
        for record in owner.result.liveries
        if record.kind == "Livery"
    ]


def saved_content_records(
    owner: Any,
    content_type: str,
) -> list[LiveryRecord | TuningRecord]:
    if not owner.result:
        return []
    if content_type == "livery":
        records = list(owner._fh6_v132_display_liveries())
        if getattr(owner, "_fh6_hidden_navigation_scope", False):
            records = [
                record
                for record in records
                if not owner._fh6_v132_is_livery_hidden(
                    owner._content_annotation_key("livery", record)
                )
            ]
        return records
    if content_type == "tuning":
        return list(owner.result.tunings)
    return []


def vehicle_brand_key(
    owner: Any,
    record: LiveryRecord | TuningRecord,
) -> tuple:
    return vehicle_brand_sort_key(record, owner._car_label)


def sorted_saved_content(
    owner: Any,
    content_type: str,
) -> list[LiveryRecord | TuningRecord]:
    records = saved_content_records(owner, content_type)
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
    if mode == "creator":
        return sort_by_creator_alias(
            records,
            owner.creator_aliases,
            lambda record: vehicle_brand_key(owner, record),
            descending=descending,
        )

    ordered = sort_records(
        records,
        SortSpec(mode=mode, descending=descending),
        owner._car_label,
    )
    if (
        content_type == "livery"
        and getattr(owner, "_fh6_v132_initial_scan_build", False)
    ):
        return [
            record
            for record in ordered
            if not isinstance(record, LiveryRecord) or record.kind == "Livery"
        ]
    return ordered
