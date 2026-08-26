from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import QStyle

from .creator_aliases import CreatorAliasStore
from .models import LiveryRecord
from .ui import MultiStatusFilterButton
from . import v1_3_2_change_view_alias_patch as _alias
from . import v1_3_2_auction_unapplied_recent_frame_fix as _auction_state


_ROW_STYLE = (
    "QPushButton { background:transparent; color:#20232d; "
    "border:1px solid transparent; border-radius:6px; "
    "padding:5px 9px; text-align:left; }"
    "QPushButton:hover { background:#f1edff; border-color:#cfc3ff; }"
    "QPushButton:checked { background:#6e4bf2; color:#ffffff; "
    "border-color:#5f39d8; font-weight:700; }"
    "QPushButton:checked:hover { background:#6441e6; border-color:#5335c7; }"
)

_FILTER_BUTTON_STYLE = (
    "QToolButton#secondaryFilterButton { background:#ffffff; color:#303341; "
    "border:1px solid #dfe1e8; border-radius:8px; padding:7px 10px; }"
    "QToolButton#secondaryFilterButton:hover { background:#f5f2ff; "
    "border-color:#9c8cf5; }"
    "QToolButton#secondaryFilterButton[fh6FilterActive=\"true\"] { "
    "background:#6e4bf2; color:#ffffff; border:2px solid #5f39d8; "
    "font-weight:700; padding:6px 9px; }"
    "QToolButton#secondaryFilterButton[fh6FilterActive=\"true\"]:hover { "
    "background:#6441e6; border-color:#5335c7; }"
)


def _actual_creator_names(window: Any) -> list[str]:
    """Names physically present in current livery/tuning records only."""
    names: dict[str, str] = {}
    result = getattr(window, "result", None)
    if result is None:
        return []
    for record in [*result.liveries, *result.tunings]:
        name = (record.header.creator or "").strip()
        if name:
            names.setdefault(name.casefold(), name)
    return sorted(names.values(), key=str.casefold)


def _observed_creator_names(window: Any) -> list[str]:
    """Actual names plus aliases that still belong to an active linked group.

    Standalone alias-only names are deliberately excluded.  Older versions
    created those singleton groups when unlinking, which left stale names in
    the editable combo boxes even though no livery/tune used them.
    """
    names: dict[str, str] = {
        name.casefold(): name for name in _actual_creator_names(window)
    }
    for group in window.creator_aliases.groups:
        all_names = group.all_names()
        if len(all_names) <= 1:
            continue
        for name in all_names:
            cleaned = (name or "").strip()
            if cleaned:
                names.setdefault(cleaned.casefold(), cleaned)
    return sorted(names.values(), key=str.casefold)


def _dissolve_alias_group(self: CreatorAliasStore, name: str) -> bool:
    """Unlink one complete creator group with one persistence write.

    The final v1.3.2 name-manager UI treats '연결 해제' as dissolving the
    selected linked group.  The previous implementation called split() once
    for every previous name, causing repeated JSON writes and leaving singleton
    alias-only groups behind.
    """
    cleaned = self._clean(name)
    group = self.find_group(cleaned)
    if group is None or len(group.all_names()) <= 1:
        return False
    try:
        self.groups.remove(group)
    except ValueError:
        return False
    self._write()
    return True


def _is_hidden(window: Any, key: str) -> bool:
    checker = getattr(window, "_fh6_v132_is_livery_hidden", None)
    if not key or not callable(checker):
        return False
    try:
        return bool(checker(window, key))
    except TypeError:
        try:
            return bool(checker(key))
        except (OSError, RuntimeError, TypeError, ValueError):
            return False
    except (OSError, RuntimeError, ValueError):
        return False


def _livery_is_unapplied_auction(window: Any, record: Any) -> bool:
    try:
        return bool(_auction_state._record_is_unapplied_auction(window, record))
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _filter_counts(window: Any, content_type: str) -> dict[int, int]:
    cards = (
        getattr(window, "_livery_grid_cards", [])
        if content_type == "livery"
        else getattr(window, "_tuning_grid_cards", [])
    )
    counts = {mode: 0 for mode in (1, 3, 4, 5, 7, 9, 10, 11, 12, 13)}

    for card in cards:
        key = str(card.property("annotationKey") or "")
        annotation = window.annotations.get(key) if key else None
        checked = bool(card.property("checked"))
        triangle = bool(card.property("triangle"))
        excluded = bool(card.property("excluded"))
        note = (annotation.note if annotation is not None else "") or ""

        counts[1] += int(checked)
        counts[5] += int(triangle)
        counts[7] += int(excluded)
        counts[10] += int(not checked and not triangle and not excluded)
        counts[3] += int(bool(note.strip()))
        counts[4] += int(not bool(note.strip()))

        if content_type != "livery":
            continue

        record = None
        resolver = getattr(window, "_record_for_content_key", None)
        if key and callable(resolver):
            try:
                record = resolver("livery", key)
            except (RuntimeError, TypeError, ValueError):
                record = None

        duplicate_fn = getattr(window, "_is_duplicate_livery", None)
        if callable(duplicate_fn):
            try:
                counts[9] += int(bool(duplicate_fn(record)))
            except (RuntimeError, TypeError, ValueError):
                pass

        counts[11] += int(_is_hidden(window, key))

        if isinstance(record, LiveryRecord) and record.kind == "SoulBoundLivery":
            unapplied = _livery_is_unapplied_auction(window, record)
            counts[13] += int(unapplied)
            counts[12] += int(not unapplied)

    return counts


def _refresh_filter_labels(window: Any, content_type: str) -> None:
    button = getattr(window, f"{content_type}_check_filter", None)
    if not isinstance(button, MultiStatusFilterButton):
        return

    counts = _filter_counts(window, content_type)
    for mode, row in button._actions.items():
        base = str(row.property("fh6FilterBaseLabel") or "").strip()
        if not base:
            base = row.text().strip()
            row.setProperty("fh6FilterBaseLabel", base)
        row.setText(f"{base} ({counts.get(int(mode), 0)})")
        row.setStyleSheet(_ROW_STYLE)

    selected = bool(button.selected_modes())
    button.setProperty("fh6FilterActive", selected)
    button.setStyleSheet(_FILTER_BUTTON_STYLE)
    style = button.style()
    if isinstance(style, QStyle):
        style.unpolish(button)
        style.polish(button)
    button.update()


def apply_v1_3_2_filter_alias_quality_patch(MainWindow: Any) -> None:
    """Add filter counts/active emphasis and make creator unlink O(1) writes."""
    if getattr(MainWindow, "_fh6_v132_filter_alias_quality_patched", False):
        return

    # The final UI's unlink action dissolves a selected group.  Make the first
    # split call dissolve the whole group; subsequent calls from the legacy loop
    # become no-ops, so persistence happens exactly once.
    CreatorAliasStore.split = _dissolve_alias_group

    # Remove stale singleton alias-only names from the name-manager candidates.
    _alias._observed_creator_names = _observed_creator_names

    original_filter_init = MultiStatusFilterButton.__init__
    original_changed = MultiStatusFilterButton._changed

    def filter_init(self: MultiStatusFilterButton, include_duplicate: bool, parent=None) -> None:
        original_filter_init(self, include_duplicate, parent)
        for row in self._actions.values():
            row.setProperty("fh6FilterBaseLabel", row.text().strip())
            row.setStyleSheet(_ROW_STYLE)
        self.setProperty("fh6FilterActive", False)
        self.setStyleSheet(_FILTER_BUTTON_STYLE)

    def changed(self: MultiStatusFilterButton) -> None:
        original_changed(self)
        active = bool(self.selected_modes())
        self.setProperty("fh6FilterActive", active)
        self.setStyleSheet(_FILTER_BUTTON_STYLE)
        style = self.style()
        if isinstance(style, QStyle):
            style.unpolish(self)
            style.polish(self)
        self.update()

    MultiStatusFilterButton.__init__ = filter_init
    MultiStatusFilterButton._changed = changed

    original_relayout_livery: Callable[..., Any] = MainWindow._relayout_livery_grid
    original_relayout_tuning: Callable[..., Any] = MainWindow._relayout_tuning_grid

    def relayout_livery(self: Any, *args: Any, **kwargs: Any):
        result = original_relayout_livery(self, *args, **kwargs)
        _refresh_filter_labels(self, "livery")
        return result

    def relayout_tuning(self: Any, *args: Any, **kwargs: Any):
        result = original_relayout_tuning(self, *args, **kwargs)
        _refresh_filter_labels(self, "tuning")
        return result

    MainWindow._relayout_livery_grid = relayout_livery
    MainWindow._relayout_tuning_grid = relayout_tuning
    MainWindow._fh6_refresh_filter_counts = _refresh_filter_labels
    MainWindow._fh6_v132_filter_alias_quality_patched = True
