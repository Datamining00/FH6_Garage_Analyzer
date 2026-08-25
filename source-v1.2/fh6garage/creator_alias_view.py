from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .models import LiveryRecord, TuningRecord

SavedRecord = LiveryRecord | TuningRecord


def sort_by_creator_alias(
    records: Iterable[SavedRecord],
    aliases: Any,
    vehicle_key: Callable[[SavedRecord], tuple],
    *,
    descending: bool = False,
) -> list[SavedRecord]:
    def key(record: SavedRecord) -> tuple:
        raw = (record.header.creator or "").strip()
        canonical = aliases.canonical_name(raw)
        return (
            1 if not raw else 0,
            canonical.casefold(),
            tuple(name.casefold() for name in aliases.search_names(raw)) if raw else (),
            vehicle_key(record),
            (record.header.name or "").casefold(),
        )

    ordered = sorted(records, key=key)
    if not descending:
        return ordered
    available = [record for record in ordered if (record.header.creator or "").strip()]
    unavailable = [record for record in ordered if not (record.header.creator or "").strip()]
    return list(reversed(available)) + unavailable


def aggregate_creator_alias_stats(result: Any, aliases: Any, missing_name: str) -> list[tuple[str, int, int]]:
    if result is None:
        return []
    stats: dict[str, list[Any]] = {}

    def bucket(raw_name: str) -> list[Any]:
        raw = (raw_name or "").strip()
        display = aliases.canonical_name(raw) if raw else missing_name
        return stats.setdefault(display.casefold() if raw else "", [display, 0, 0])

    for record in result.liveries:
        if record.kind == "Livery":
            bucket(record.header.creator or "")[1] += 1
    for record in result.tunings:
        bucket(record.header.creator or "")[2] += 1

    rows = [(str(value[0]), int(value[1]), int(value[2])) for value in stats.values()]
    rows.sort(key=lambda row: (row[0] == missing_name, row[0].casefold()))
    return rows
