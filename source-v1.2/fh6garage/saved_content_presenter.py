from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar

from .models import LiveryRecord, TuningRecord
from .saved_content_view import group_items


SavedContentRecord = LiveryRecord | TuningRecord
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FilterState:
    checked: bool = False
    note: str = ""
    triangle: bool = False
    excluded: bool = False
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class GridSection:
    key: str
    label: str
    items: tuple[T, ...]


def filter_matches(
    content_type: str,
    selected_modes: Iterable[int],
    state: FilterState,
) -> bool:
    """Evaluate saved-content status filters without reading Qt controls."""

    has_note = bool(state.note.strip())
    checks = {
        1: state.checked,
        2: not state.checked,
        3: has_note,
        4: not has_note,
        5: state.triangle,
        6: not state.triangle,
        7: state.excluded,
        8: not state.excluded,
        9: state.duplicate if content_type == "livery" else True,
        10: not state.checked and not state.triangle and not state.excluded,
    }
    return all(checks.get(mode, True) for mode in selected_modes)


def build_search_text(
    record: SavedContentRecord,
    car_label: Callable[[int | None], str],
    note: str = "",
) -> str:
    return " ".join(
        (
            record.header.name or "",
            record.header.creator or "",
            str(record.header.car_id or ""),
            car_label(record.header.car_id),
            record.header.description or "",
            note or "",
        )
    ).casefold()


def search_matches(search_text: str, query: str) -> bool:
    needle = query.strip().casefold()
    return not needle or needle in search_text.casefold()


def build_grid_sections(
    items: Iterable[T],
    *,
    group_mode: str,
    vehicle_key: Callable[[T], str],
    vehicle_label: Callable[[T], str],
    creator_key: Callable[[T], str],
    creator_label: Callable[[T], str],
) -> list[GridSection]:
    """Build an ordered layout plan; Qt only renders the returned sections."""

    source = list(items)
    if group_mode == "none":
        return [GridSection("", "", tuple(source))]
    if group_mode == "creator":
        grouped = group_items(source, creator_key, creator_label)
    elif group_mode == "vehicle":
        grouped = group_items(source, vehicle_key, vehicle_label)
    else:
        raise ValueError(f"Unsupported saved-content group mode: {group_mode}")
    return [
        GridSection(key, label, tuple(group))
        for key, label, group in grouped
    ]
