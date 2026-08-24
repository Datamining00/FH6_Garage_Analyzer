from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QPushButton, QToolButton, QWidget, QWidgetAction

from .i18n import get_language
from .models import LiveryRecord
from .ui import MultiStatusFilterButton
from .v1_3_2_visibility_patch import _eye_slash_pixmap


_HIDDEN_MODE = 11
_AUCTION_APPLIED_MODE = 12
_AUCTION_UNAPPLIED_MODE = 13


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


def _remove_filter_mode(button: MultiStatusFilterButton, mode: int) -> None:
    row = button._actions.pop(mode, None)
    menu = button.menu()
    if row is None or menu is None:
        return
    for action in tuple(menu.actions()):
        if isinstance(action, QWidgetAction) and action.defaultWidget() is row:
            menu.removeAction(action)
            action.deleteLater()
            break
    row.hide()
    row.deleteLater()


class _HideButtonAligner(QObject):
    """Keep the card hide button centered on the right-side fourth action."""

    _WATCHED_EVENTS = {
        QEvent.Type.Show,
        QEvent.Type.Resize,
        QEvent.Type.LayoutRequest,
    }

    def __init__(
        self,
        overlay: QWidget,
        hide_button: QToolButton,
        target_button: QToolButton,
        info_button: QToolButton,
    ) -> None:
        super().__init__(overlay)
        self.overlay = overlay
        self.hide_button = hide_button
        self.target_button = target_button
        self.info_button = info_button
        overlay.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._WATCHED_EVENTS:
            QTimer.singleShot(0, self.reposition)
        return False

    def reposition(self) -> None:
        if (
            self.overlay is None
            or self.hide_button is None
            or self.target_button is None
            or self.info_button is None
        ):
            return
        target_geometry = self.target_button.geometry()
        info_geometry = self.info_button.geometry()
        if target_geometry.width() <= 0 or info_geometry.width() <= 0:
            return
        x = info_geometry.x() + (
            info_geometry.width() - self.hide_button.width()
        ) // 2
        y = target_geometry.center().y() - self.hide_button.height() // 2
        self.hide_button.move(max(0, x), max(0, y))
        self.hide_button.raise_()


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
        _eye_slash_pixmap(False),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    icon.addPixmap(
        _eye_slash_pixmap(True),
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

    aligner = _HideButtonAligner(
        overlay,
        hide_button,
        zoom_button,
        info_button,
    )
    card._fh6_hide_button = hide_button
    card._fh6_hide_aligner = aligner
    QTimer.singleShot(0, aligner.reposition)


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


def apply_v1_3_2_ui_cleanup_patch(MainWindow) -> None:
    """Apply the final v1.3.2 visibility and top-toolbar UX cleanup."""
    if getattr(MainWindow, "_fh6_v132_ui_cleanup_patched", False):
        return

    original_filter_init = MultiStatusFilterButton.__init__
    original_build_ui = MainWindow._build_ui
    original_make_card = MainWindow._make_saved_content_card
    original_layout_visible_grid_cards = MainWindow._layout_visible_grid_cards
    original_filter_saved_content_table = MainWindow._filter_saved_content_table

    def filter_init(self, include_duplicate: bool, parent=None) -> None:
        original_filter_init(self, include_duplicate, parent)
        if include_duplicate:
            _remove_filter_mode(self, _AUCTION_APPLIED_MODE)

    MultiStatusFilterButton.__init__ = filter_init

    def refresh_all(self) -> None:
        # refresh_scan reloads the vehicle DB and re-scans the live save. The
        # existing v1.3.2 scan-finished patch then re-resolves CacheThumbnails,
        # rebuilds livery/tuning views and refreshes summary counts.
        self.refresh_scan()

    def patched_build_ui(self) -> None:
        original_build_ui(self)
        _normalize_path_rows(self)

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery":
            _install_card_hide_button(self, card, key)
        return card

    def normal_view_allows(self, card: Any) -> bool:
        modes = self.livery_check_filter.selected_modes()
        if _AUCTION_UNAPPLIED_MODE in modes:
            return True
        key = str(card.property("annotationKey") or "")
        record = self._record_for_content_key("livery", key) if key else None
        if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
            return True
        return bool(self._fh6_v132_is_auction_applied(record))

    def patched_layout_visible_grid_cards(
        self,
        content_type: str,
        cards,
    ) -> None:
        if content_type == "livery":
            cards = [card for card in cards if normal_view_allows(self, card)]
        original_layout_visible_grid_cards(self, content_type, cards)

    def patched_filter_saved_content_table(
        self,
        content_type: str,
        text: str,
    ) -> None:
        original_filter_saved_content_table(self, content_type, text)
        if content_type != "livery":
            return
        modes = self.livery_check_filter.selected_modes()
        if _AUCTION_UNAPPLIED_MODE in modes:
            return

        table = self.livery_table
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            key_item = table.item(row, 0)
            key = (
                str(key_item.data(Qt.ItemDataRole.UserRole) or "")
                if key_item is not None
                else ""
            )
            record = (
                self._record_for_content_key("livery", key)
                if key
                else None
            )
            if (
                isinstance(record, LiveryRecord)
                and record.kind == "SoulBoundLivery"
                and not self._fh6_v132_is_auction_applied(record)
            ):
                table.setRowHidden(row, True)

    MainWindow._fh6_v132_refresh_all = refresh_all
    MainWindow._build_ui = patched_build_ui
    MainWindow._make_saved_content_card = patched_make_card
    MainWindow._layout_visible_grid_cards = patched_layout_visible_grid_cards
    MainWindow._filter_saved_content_table = patched_filter_saved_content_table
    MainWindow._fh6_v132_ui_cleanup_patched = True
