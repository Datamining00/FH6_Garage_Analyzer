from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from .models import LiveryRecord, TuningRecord


SavedContentRecord = LiveryRecord | TuningRecord
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SortSpec:
    mode: str = "default"
    descending: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"default", "brand", "creator", "download"}:
            raise ValueError(f"Unsupported saved-content sort mode: {self.mode}")


def vehicle_brand_sort_key(
    record: SavedContentRecord,
    car_label: Callable[[int | None], str],
) -> tuple[Any, ...]:
    """Return the stable manufacturer-first key used by both content views."""

    label = car_label(record.header.car_id).strip()
    unknown = label.startswith("Car ID ") or label == "Unknown vehicle"
    parts = label.split(maxsplit=1)
    brand_first = (
        parts[1]
        if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 4
        else label
    ).casefold()
    return (
        1 if unknown else 0,
        brand_first,
        label.casefold(),
        (record.header.name or "").casefold(),
    )


def sort_records(
    records: Iterable[SavedContentRecord],
    spec: SortSpec,
    car_label: Callable[[int | None], str],
) -> list[SavedContentRecord]:
    """Sort records without reading or mutating Qt widget state."""

    source = list(records)
    vehicle_key = lambda record: vehicle_brand_sort_key(record, car_label)

    if spec.mode == "brand":
        ordered = sorted(source, key=vehicle_key)
        return list(reversed(ordered)) if spec.descending else ordered

    if spec.mode == "creator":
        def creator_key(record: SavedContentRecord) -> tuple[Any, ...]:
            creator = (record.header.creator or "").strip()
            return (
                1 if not creator else 0,
                creator.casefold(),
                vehicle_key(record),
                (record.header.name or "").casefold(),
            )

        ordered = sorted(source, key=creator_key)
        if not spec.descending:
            return ordered
        available = [
            record
            for record in ordered
            if (record.header.creator or "").strip()
        ]
        unavailable = [
            record
            for record in ordered
            if not (record.header.creator or "").strip()
        ]
        return list(reversed(available)) + unavailable

    if spec.mode == "download":
        available = [record for record in source if record.downloaded_at is not None]
        unavailable = [record for record in source if record.downloaded_at is None]
        return sorted(
            available,
            key=lambda record: record.downloaded_at or 0.0,
            reverse=spec.descending,
        ) + unavailable

    return list(reversed(source)) if spec.descending else source


def creator_alias_token(aliases: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return a hashable alias revision without coupling to its storage class."""

    return tuple(
        (
            str(getattr(group, "current", "")),
            tuple(str(name) for name in getattr(group, "previous", ())),
        )
        for group in getattr(aliases, "groups", ())
    )


def sort_cache_key(
    *,
    content_type: str,
    result: object | None,
    records: Sequence[SavedContentRecord],
    spec: SortSpec,
    initial_scan: bool,
    car_db_revision: int,
    aliases: Any,
) -> tuple[Any, ...]:
    """Build the complete invalidation key for the derived record order."""

    return (
        content_type,
        id(result),
        tuple(id(record) for record in records),
        spec.mode,
        spec.descending,
        initial_scan,
        car_db_revision,
        creator_alias_token(aliases),
    )


def group_items(
    items: Iterable[T],
    key: Callable[[T], str],
    label: Callable[[T], str],
) -> list[tuple[str, str, list[T]]]:
    """Group items in first-seen order for predictable grid placement."""

    positions: dict[str, int] = {}
    groups: list[tuple[str, str, list[T]]] = []
    for item in items:
        group_key = key(item)
        position = positions.get(group_key)
        if position is None:
            positions[group_key] = len(groups)
            groups.append((group_key, label(item), [item]))
        else:
            groups[position][2].append(item)
    return groups
