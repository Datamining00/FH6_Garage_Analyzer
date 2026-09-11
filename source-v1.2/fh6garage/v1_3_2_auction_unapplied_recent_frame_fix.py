from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QWidget

from . import v1_3_2_change_dialog_folder_patch as _change_dialog
from . import v1_3_2_responsiveness_sort_patch as _responsive


_AUCTION_APPLIED_MODE = 12
_AUCTION_UNAPPLIED_MODE = 13
_MEMORY_FILTER_DEFAULT = "DEFAULT"
_RECENT_CARD_FRAME_RULE = (
    "QFrame#panel, QFrame#card { "
    "background:#ffffff; border:1px solid #cfd3dd; border-radius:12px; "
    "}"
)


def _selected_modes(window: Any) -> set[int]:
    filter_button = getattr(window, "livery_check_filter", None)
    selected = getattr(filter_button, "selected_modes", None)
    if not callable(selected):
        return set()
    try:
        return {int(mode) for mode in selected()}
    except (TypeError, ValueError, RuntimeError):
        return set()


def _memory_state_usable(window: Any) -> bool:
    checker = getattr(window, "_fh6_memory_state_usable", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except (RuntimeError, TypeError, ValueError):
        return False


def _memory_filter_mode(window: Any) -> str:
    return str(
        getattr(window, "_fh6_memory_livery_filter_mode", _MEMORY_FILTER_DEFAULT)
        or _MEMORY_FILTER_DEFAULT
    )


def _record_is_unapplied_auction(window: Any, record: Any) -> bool:
    """Use memory state when available; otherwise retain the v1.3.2 cache rule."""
    if getattr(record, "kind", None) != "SoulBoundLivery":
        return False

    if _memory_state_usable(window):
        state_fn = getattr(window, "_fh6_memory_livery_state_for_record", None)
        if callable(state_fn):
            try:
                return state_fn(record) == "unapplied"
            except (OSError, RuntimeError, TypeError, ValueError):
                return False

    applied_fn = getattr(window, "_fh6_v132_is_auction_applied", None)
    if not callable(applied_fn):
        return True
    try:
        return not bool(applied_fn(record))
    except (OSError, RuntimeError, TypeError, ValueError):
        return True


def _card_record(window: Any, card: Any) -> Any:
    key = str(card.property("annotationKey") or "") if card is not None else ""
    resolver = getattr(window, "_record_for_content_key", None)
    if not key or not callable(resolver):
        return None
    try:
        return resolver("livery", key)
    except (RuntimeError, TypeError, ValueError):
        return None


def _default_auction_visibility_allowed(
    window: Any,
    card: Any,
    base_allowed: bool,
) -> bool:
    """Default view excludes only confirmed-unapplied SoulBound liveries."""
    if not base_allowed:
        return False

    modes = _selected_modes(window)
    if _AUCTION_APPLIED_MODE in modes or _AUCTION_UNAPPLIED_MODE in modes:
        return True

    if (
        _memory_state_usable(window)
        and _memory_filter_mode(window) != _MEMORY_FILTER_DEFAULT
    ):
        return True

    record = _card_record(window, card)
    if _record_is_unapplied_auction(window, record):
        return False
    return True


def _strengthen_recent_card_frames(root: QWidget) -> QWidget:
    frames: list[QFrame] = []
    if isinstance(root, QFrame):
        frames.append(root)
    frames.extend(root.findChildren(QFrame))

    for frame in frames:
        if frame.objectName() not in {"panel", "card"}:
            continue
        if bool(frame.property("fh6RecentStrongFrame")):
            continue
        existing = frame.styleSheet().rstrip()
        frame.setStyleSheet(
            (existing + "\n" if existing else "") + _RECENT_CARD_FRAME_RULE
        )
        frame.setProperty("fh6RecentStrongFrame", True)
    return root


def apply_v1_3_2_auction_unapplied_recent_frame_fix(MainWindow: Any) -> None:
    """Enforce default auction visibility and clearer recent-card borders."""
    if getattr(MainWindow, "_fh6_v132_auction_unapplied_recent_frame_fixed", False):
        return

    original_allowed: Callable[[Any, Any], bool] = _responsive._livery_visibility_allowed
    original_table_filter = MainWindow._filter_saved_content_table
    original_single_change = _change_dialog._single_change_item
    original_changed_pair = _change_dialog._changed_pair_item

    def livery_visibility_allowed(self: Any, card: Any) -> bool:
        return _default_auction_visibility_allowed(
            self,
            card,
            bool(original_allowed(self, card)),
        )

    def filter_saved_content_table(self: Any, content_type: str, text: str) -> None:
        original_table_filter(self, content_type, text)
        if content_type != "livery":
            return

        modes = _selected_modes(self)
        if _AUCTION_APPLIED_MODE in modes or _AUCTION_UNAPPLIED_MODE in modes:
            return

        if (
            _memory_state_usable(self)
            and _memory_filter_mode(self) != _MEMORY_FILTER_DEFAULT
        ):
            return

        table = getattr(self, "livery_table", None)
        resolver = getattr(self, "_record_for_content_key", None)
        if table is None or not callable(resolver):
            return

        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            key_item = table.item(row, 0)
            key = (
                str(key_item.data(Qt.ItemDataRole.UserRole) or "")
                if key_item is not None
                else ""
            )
            if not key:
                continue
            try:
                record = resolver("livery", key)
            except (RuntimeError, TypeError, ValueError):
                record = None
            if _record_is_unapplied_auction(self, record):
                table.setRowHidden(row, True)

    def single_change_item(*args: Any, **kwargs: Any):
        widget, status, span = original_single_change(*args, **kwargs)
        _strengthen_recent_card_frames(widget)
        return widget, status, span

    def changed_pair_item(*args: Any, **kwargs: Any):
        widget, status, span = original_changed_pair(*args, **kwargs)
        _strengthen_recent_card_frames(widget)
        return widget, status, span

    _responsive._livery_visibility_allowed = livery_visibility_allowed
    MainWindow._filter_saved_content_table = filter_saved_content_table
    _change_dialog._single_change_item = single_change_item
    _change_dialog._changed_pair_item = changed_pair_item
    MainWindow._fh6_v132_auction_unapplied_recent_frame_fixed = True
