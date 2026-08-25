from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from .i18n import get_language
from .livery_visibility import eye_slash_pixmap


def _t(key: str) -> str:
    ko = (get_language() or "ko").lower().startswith("ko")
    table = {
        "refresh_all": ("전체 새로고침", "Refresh all"),
        "hide_toggle": ("이 리버리 숨기기", "Hide this livery"),
    }
    value = table[key]
    return value[0] if ko else value[1]


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


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
    buttons: list[QPushButton] = []
    if layout is None:
        return buttons
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QPushButton):
            buttons.append(widget)
    return buttons


def _remove_direct_labels(layout: Any) -> None:
    if layout is None:
        return
    for index in reversed(range(layout.count())):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QLabel):
            layout.removeWidget(widget)
            widget.hide()
            widget.deleteLater()


def _install_card_hide_button(self: Any, card: Any, key: str) -> None:
    if getattr(card, "_fh6_hide_button", None) is not None:
        return

    image_label = getattr(card, "_fh6_image_label", None)
    zoom_button = getattr(card, "_fh6_zoom_button", None)
    info_button = getattr(card, "_fh6_info_button", None)
    if image_label is None or zoom_button is None or info_button is None:
        return

    image_host = image_label.parentWidget()
    stack = image_host.layout() if image_host is not None else None
    overlay = stack.currentWidget() if stack is not None and hasattr(stack, "currentWidget") else None
    if overlay is None:
        return

    hide_button = QToolButton(overlay)
    hide_button.setCheckable(True)
    icon = QIcon()
    icon.addPixmap(
        eye_slash_pixmap(False),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    icon.addPixmap(
        eye_slash_pixmap(True),
        QIcon.Mode.Normal,
        QIcon.State.On,
    )
    hide_button.setIcon(icon)
    hide_button.setIconSize(zoom_button.iconSize())
    hide_button.setChecked(self._fh6_v132_is_livery_hidden(key))
    hide_button.setToolTip(_t("hide_toggle"))
    hide_button.setAccessibleName(_t("hide_toggle"))
    hide_button.setFixedSize(38, 38)
    hide_button.setCursor(Qt.CursorShape.PointingHandCursor)
    hide_button.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,242); "
        "border:1px solid #dfe1e8; border-radius:9px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:#f2edff; }"
        "QToolButton:checked { border-color:#8c74ee; background:#eee9ff; }"
    )
    hide_button.toggled.connect(
        lambda enabled, k=key: self._fh6_v132_set_livery_hidden(k, enabled)
    )

    card._fh6_hide_button = hide_button


def _normalize_path_rows(self: Any) -> None:
    content = self.path_edit.parentWidget()
    root_layout = content.layout() if content is not None else None
    if root_layout is None or not hasattr(self, "cache_path_edit"):
        return

    save_row = _layout_with_widget(root_layout, self.path_edit)
    cache_row = _layout_with_widget(root_layout, self.cache_path_edit)
    if save_row is None or cache_row is None:
        return

    # The two path rows use the same three-column geometry:
    # path | path selector | action slot.
    _remove_direct_labels(cache_row)
    save_row.setContentsMargins(0, 0, 0, 0)
    cache_row.setContentsMargins(0, 0, 0, 0)
    save_row.setSpacing(8)
    cache_row.setSpacing(8)

    save_buttons = _direct_buttons(save_row)
    cache_buttons = _direct_buttons(cache_row)
    if len(save_buttons) < 2 or not cache_buttons:
        return

    save_choose = save_buttons[0]
    refresh_button = save_buttons[-1]
    cache_choose = cache_buttons[0]
    cache_extra = cache_buttons[1:]

    refresh_button.setText(_t("refresh_all"))
    refresh_button.setObjectName("secondary")
    try:
        refresh_button.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass
    refresh_button.clicked.connect(
        lambda _checked=False: self._fh6_v132_refresh_all()
    )

    # Path-selector buttons form one visual column.
    cache_choose.setObjectName("primary")
    selector_width = max(
        save_choose.sizeHint().width(),
        cache_choose.sizeHint().width(),
    )
    save_choose.setFixedWidth(selector_width)
    cache_choose.setFixedWidth(selector_width)
    _repolish(cache_choose)

    for widget in (
        self.path_edit,
        self.cache_path_edit,
        save_choose,
        cache_choose,
        refresh_button,
    ):
        widget.setMinimumHeight(36)

    # The second-row right slot is intentionally empty. Reserve the exact
    # width of the refresh action for the future backup button.
    for button in cache_extra:
        cache_row.removeWidget(button)
        button.hide()
        button.deleteLater()

    action_width = max(1, refresh_button.sizeHint().width())
    refresh_button.setFixedWidth(action_width)
    cache_row.addSpacing(action_width)

    save_row.setStretchFactor(self.path_edit, 1)
    cache_row.setStretchFactor(self.cache_path_edit, 1)

    self.full_refresh_button = refresh_button
    self._fh6_v132_reserved_backup_slot_width = action_width


def _widget_index(layout: Any, target: QWidget) -> int:
    if layout is None:
        return -1
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is not None and item.widget() is target:
            return index
    return -1


def _remove_items_after(layout: Any, index: int) -> None:
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
    """Use fixed widgets for exact save/cache toolbar column alignment."""
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
    selector_width = max(save_choose.sizeHint().width(), cache_choose.sizeHint().width())
    save_choose.setFixedWidth(selector_width)
    cache_choose.setFixedWidth(selector_width)
    action_width = max(1, refresh_button.sizeHint().width())
    refresh_button.setFixedWidth(action_width)
    _remove_items_after(cache_row, _widget_index(cache_row, cache_choose))
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
    from .release_layout import _compact_change_banner, _move_change_banner_to_reserved_slot

    _move_change_banner_to_reserved_slot(self)
    _compact_change_banner(self)

    def finalize_geometry() -> None:
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
    """Normalize My Designs/Auction controls into an exclusive selection."""
    saved = getattr(self, "livery_my_designs_toggle", None)
    auction = getattr(self, "livery_auction_toggle", None)
    if not isinstance(saved, QPushButton) or not isinstance(auction, QPushButton):
        return
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
    setter = getattr(self, "_fh6_v132_set_source_enabled", None)
    if callable(setter):
        setter("my_designs", saved.isChecked())
        setter("auction", auction.isChecked())
