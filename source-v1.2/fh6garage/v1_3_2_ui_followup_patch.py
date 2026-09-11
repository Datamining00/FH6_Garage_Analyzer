from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QPushButton,
    QSizePolicy,
    QWidget,
)


def _layout_with_widget(root_layout: Any, target: QWidget):
    if root_layout is None:
        return None
    for index in range(root_layout.count()):
        item = root_layout.itemAt(index)
        layout = item.layout() if item is not None else None
        if layout is None:
            continue
        for child_index in range(layout.count()):
            child_item = layout.itemAt(child_index)
            if child_item is not None and child_item.widget() is target:
                return layout
    return None


def _direct_buttons(layout: Any) -> list[QPushButton]:
    result: list[QPushButton] = []
    if layout is None:
        return result
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QPushButton):
            result.append(widget)
    return result


def _widget_index(layout: Any, target: QWidget) -> int:
    if layout is None:
        return -1
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is not None and item.widget() is target:
            return index
    return -1


def _remove_items_after(layout: Any, index: int) -> None:
    """Remove stale spacer/action-slot items after one layout item."""
    if layout is None or index < 0:
        return
    for child_index in reversed(range(index + 1, layout.count())):
        item = layout.takeAt(child_index)
        if item is None:
            continue
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()


def _align_path_rows(self: Any) -> None:
    """Make save/cache path rows share exact right-column geometry.

    The previous implementation used QBoxLayout.addSpacing() for the empty
    backup slot. That spacer is not a true fixed-width widget and can produce
    an 8 px visual drift after style/layout negotiation on Windows. Replace it
    with a fixed widget whose width exactly mirrors the refresh button.
    """
    if not hasattr(self, "path_edit") or not hasattr(self, "cache_path_edit"):
        return

    content = self.path_edit.parentWidget()
    root_layout = content.layout() if content is not None else None
    if root_layout is None:
        return

    save_row = _layout_with_widget(root_layout, self.path_edit)
    cache_row = _layout_with_widget(root_layout, self.cache_path_edit)
    if save_row is None or cache_row is None:
        return

    save_buttons = _direct_buttons(save_row)
    cache_buttons = _direct_buttons(cache_row)
    if len(save_buttons) < 2 or not cache_buttons:
        return

    save_choose = save_buttons[0]
    refresh_button = save_buttons[-1]
    cache_choose = cache_buttons[0]

    save_row.setContentsMargins(0, 0, 0, 0)
    cache_row.setContentsMargins(0, 0, 0, 0)
    save_row.setSpacing(8)
    cache_row.setSpacing(8)

    selector_width = max(
        save_choose.sizeHint().width(),
        cache_choose.sizeHint().width(),
    )
    save_choose.setFixedWidth(selector_width)
    cache_choose.setFixedWidth(selector_width)

    action_width = max(1, refresh_button.sizeHint().width())
    refresh_button.setFixedWidth(action_width)

    cache_choose_index = _widget_index(cache_row, cache_choose)
    _remove_items_after(cache_row, cache_choose_index)

    reserved_slot = QWidget(content)
    reserved_slot.setObjectName("fh6ReservedBackupSlot")
    reserved_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    reserved_slot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    reserved_slot.setFixedWidth(action_width)
    reserved_slot.setMinimumHeight(refresh_button.minimumHeight())
    cache_row.addWidget(reserved_slot)

    self.path_edit.setMinimumWidth(0)
    self.cache_path_edit.setMinimumWidth(0)
    save_row.setStretchFactor(self.path_edit, 1)
    cache_row.setStretchFactor(self.cache_path_edit, 1)
    self._fh6_v132_reserved_backup_slot = reserved_slot

    # Repeat after the first native Windows layout pass. This converts any
    # style-dependent size-hint difference into the exact same fixed geometry.
    def finalize_geometry() -> None:
        if not save_choose or not cache_choose or not refresh_button:
            return
        selector = max(
            save_choose.width(),
            cache_choose.width(),
            save_choose.sizeHint().width(),
            cache_choose.sizeHint().width(),
        )
        action = max(refresh_button.width(), refresh_button.sizeHint().width(), 1)
        save_choose.setFixedWidth(selector)
        cache_choose.setFixedWidth(selector)
        refresh_button.setFixedWidth(action)
        reserved_slot.setFixedWidth(action)

    QTimer.singleShot(0, finalize_geometry)


def _configure_livery_source_switch(self: Any) -> None:
    """Make My Designs/Auction an exact-one selection instead of two toggles."""
    saved = getattr(self, "livery_my_designs_toggle", None)
    auction = getattr(self, "livery_auction_toggle", None)
    if not isinstance(saved, QPushButton) or not isinstance(auction, QPushButton):
        return

    # Preserve a valid prior single selection. Legacy states with both on or
    # both off resolve deterministically to My Designs.
    auction_only = auction.isChecked() and not saved.isChecked()
    saved.blockSignals(True)
    auction.blockSignals(True)
    saved.setChecked(not auction_only)
    auction.setChecked(auction_only)
    saved.blockSignals(False)
    auction.blockSignals(False)

    group = QButtonGroup(self)
    group.setExclusive(True)
    group.addButton(saved)
    group.addButton(auction)
    self._fh6_v132_livery_source_group = group

    # Persist the normalized legacy state. During _build_ui result is still
    # None, so this does not trigger a scan or table rebuild.
    setter = getattr(self, "_fh6_v132_set_source_enabled", None)
    if callable(setter):
        setter("my_designs", saved.isChecked())
        setter("auction", auction.isChecked())


def apply_v1_3_2_ui_followup_patch(MainWindow) -> None:
    """Final v1.3.2 follow-up for exact toolbar geometry and source selection."""
    if getattr(MainWindow, "_fh6_v132_ui_followup_patched", False):
        return

    original_build_ui = MainWindow._build_ui

    def patched_build_ui(self) -> None:
        original_build_ui(self)
        _align_path_rows(self)
        _configure_livery_source_switch(self)

    MainWindow._build_ui = patched_build_ui
    MainWindow._fh6_v132_ui_followup_patched = True
