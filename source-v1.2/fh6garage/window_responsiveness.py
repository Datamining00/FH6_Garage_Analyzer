from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtWidgets import QApplication


WINDOW_GEOMETRY_KEY = "window_geometry_v1_3_1"
WINDOW_MAXIMIZED_KEY = "window_maximized_v1_3_1"
RESIZE_DEBOUNCE_MS = 110
CARD_WIDTH_UPDATE_STEP = 4


def _content_page_index(content_type: str) -> int:
    return 1 if content_type == "livery" else 2


def _grid_objects(self: Any, content_type: str):
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    host = getattr(self, f"{content_type}_grid_host", None)
    cards = getattr(self, f"_{content_type}_grid_cards", None)
    return scroll, layout, host, cards


def _cards_currently_in_layout(self: Any, content_type: str) -> list:
    """Return the logically visible cards without re-running search/filter logic.

    The grid layout contains only cards that passed the current search/filter.
    Reading the layout is much cheaper than re-evaluating every card, and also
    works while the stacked page itself is hidden.
    """
    _scroll, layout, _host, cards = _grid_objects(self, content_type)
    if layout is None or not cards:
        return []

    by_id = {id(card): card for card in cards}
    ordered: list = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if widget is None:
            continue
        card = by_id.get(id(widget))
        if card is not None:
            ordered.append(card)
    return ordered


def _apply_grid_card_widths(
    self: Any,
    content_type: str,
    columns: int,
    *,
    force: bool = False,
) -> None:
    scroll, layout, host, cards = _grid_objects(self, content_type)
    if scroll is None or layout is None or host is None or cards is None:
        return
    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return

    columns = max(2, min(4, int(columns)))
    margins = layout.contentsMargins()
    gap = max(0, layout.horizontalSpacing())
    available = (
        viewport.width()
        - margins.left()
        - margins.right()
        - gap * (columns - 1)
        - 4
    )
    card_width = max(1, available // columns)

    last_attr = f"_fh6_v131_{content_type}_card_width"
    last_width = getattr(self, last_attr, None)
    if (
        not force
        and isinstance(last_width, int)
        and abs(card_width - last_width) < CARD_WIDTH_UPDATE_STEP
    ):
        return

    for column in range(4):
        stretch = 1 if column < columns else 0
        if layout.columnStretch(column) != stretch:
            layout.setColumnStretch(column, stretch)

    for card in cards:
        if card.minimumWidth() != card_width or card.maximumWidth() != card_width:
            card.setFixedWidth(card_width)

    setattr(self, last_attr, card_width)
    host.setMinimumWidth(0)
    host.updateGeometry()


def _lightweight_reflow(self: Any, content_type: str) -> bool:
    """Repack the already-visible cards for a new column count.

    This deliberately avoids _relayout_*(), which re-runs search, annotation,
    duplicate and filter checks for every card. A pure window resize cannot
    change those results, so only widget positions need to be updated.
    """
    scroll, layout, host, _cards = _grid_objects(self, content_type)
    if scroll is None or layout is None or host is None:
        return False

    target_columns = self._fh6_grid_column_count(content_type)
    active_attr = f"_fh6_{content_type}_grid_columns"
    active_columns = getattr(self, active_attr, target_columns)
    if int(active_columns) == int(target_columns):
        _apply_grid_card_widths(
            self,
            content_type,
            target_columns,
            force=True,
        )
        return False

    visible_cards = _cards_currently_in_layout(self, content_type)
    scrollbar = scroll.verticalScrollBar()
    old_scroll = scrollbar.value()

    host.setUpdatesEnabled(False)
    try:
        if content_type == "livery":
            self._clear_livery_grid_layout()
        else:
            self._clear_tuning_grid_layout()

        # v1.3's generalized layout routine recalculates the target column
        # count and supports both vehicle and creator grouping.
        self._layout_visible_grid_cards(content_type, visible_cards)
        layout.activate()
        _apply_grid_card_widths(
            self,
            content_type,
            target_columns,
            force=True,
        )
    finally:
        host.setUpdatesEnabled(True)

    host.update()
    if hasattr(self, "_restore_grid_scroll"):
        self._restore_grid_scroll(scrollbar, old_scroll)
    else:
        scrollbar.setValue(min(old_scroll, scrollbar.maximum()))
    return True


def _ensure_resize_timer(self: Any) -> QTimer:
    timer = getattr(self, "_fh6_v131_resize_timer", None)
    if timer is not None:
        return timer

    timer = QTimer(self)
    timer.setSingleShot(True)
    timer.setInterval(RESIZE_DEBOUNCE_MS)
    timer.timeout.connect(self._fh6_v131_finalize_resize)
    self._fh6_v131_resize_timer = timer
    return timer


def _schedule_resize_settle(self: Any) -> None:
    if getattr(self, "_fh6_v131_finalizing_resize", False):
        return
    _ensure_resize_timer(self).start()


def _finalize_resize(self: Any) -> None:
    if getattr(self, "_fh6_v131_finalizing_resize", False):
        return

    self._fh6_v131_finalizing_resize = True
    try:
        page_index = self.pages.currentIndex() if hasattr(self, "pages") else -1
        if page_index == 1:
            _lightweight_reflow(self, "livery")
            active = getattr(
                self,
                "_fh6_livery_grid_columns",
                self._fh6_grid_column_count("livery"),
            )
            _apply_grid_card_widths(self, "livery", active, force=True)
            self._refresh_visible_livery_thumbnails()
        elif page_index == 2:
            _lightweight_reflow(self, "tuning")
            active = getattr(
                self,
                "_fh6_tuning_grid_columns",
                self._fh6_grid_column_count("tuning"),
            )
            _apply_grid_card_widths(self, "tuning", active, force=True)
            self._refresh_visible_tuning_thumbnails()
    finally:
        self._fh6_v131_finalizing_resize = False


def _optimized_sync_grid_widths(self: Any, content_type: str) -> None:
    scroll, layout, _host, _cards = _grid_objects(self, content_type)
    if scroll is None or layout is None:
        return

    target_columns = self._fh6_grid_column_count(content_type)
    active_attr = f"_fh6_{content_type}_grid_columns"
    active_columns = getattr(self, active_attr, target_columns)

    timer = getattr(self, "_fh6_v131_resize_timer", None)
    resizing = bool(timer is not None and timer.isActive())

    # During a drag keep the current layout stable and defer the expensive
    # 2->3 / 3->4 transition until resize events settle. Outside a resize,
    # such as when a hidden page is first shown, apply the reflow immediately.
    if int(target_columns) != int(active_columns) and not resizing:
        _lightweight_reflow(self, content_type)
        active_columns = getattr(self, active_attr, target_columns)

    _apply_grid_card_widths(
        self,
        content_type,
        int(active_columns),
        force=not resizing,
    )


def _save_window_geometry(self: Any) -> None:
    if not hasattr(self, "settings"):
        return

    if self.isMaximized() or self.isMinimized():
        rect = self.normalGeometry()
    else:
        rect = self.geometry()

    if isinstance(rect, QRect) and rect.isValid() and rect.width() > 0 and rect.height() > 0:
        self.settings.setValue(WINDOW_GEOMETRY_KEY, rect)
    self.settings.setValue(WINDOW_MAXIMIZED_KEY, self.isMaximized())
    self.settings.sync()


def _correct_geometry_to_screens(self: Any, rect: QRect) -> QRect:
    screens = QApplication.screens()
    if not screens:
        return QRect(rect)

    candidate = QRect(rect)
    # A small visible intersection is enough to let the user recover/move the
    # window manually; otherwise treat the saved monitor as unavailable.
    for screen in screens:
        available = screen.availableGeometry()
        intersection = available.intersected(candidate)
        if intersection.width() >= 64 and intersection.height() >= 64:
            return candidate

    primary = QApplication.primaryScreen() or screens[0]
    available = primary.availableGeometry()
    width = min(max(1, candidate.width()), max(1, available.width()))
    height = min(max(1, candidate.height()), max(1, available.height()))
    x = available.x() + max(0, (available.width() - width) // 2)
    y = available.y() + max(0, (available.height() - height) // 2)
    return QRect(x, y, width, height)


def _restore_window_geometry(self: Any) -> bool:
    if not hasattr(self, "settings"):
        return False

    stored = self.settings.value(WINDOW_GEOMETRY_KEY)
    if not isinstance(stored, QRect) or not stored.isValid():
        return False

    corrected = _correct_geometry_to_screens(self, stored)
    self.setGeometry(corrected)
    if self.settings.value(WINDOW_MAXIMIZED_KEY, False, bool):
        self.setWindowState(
            self.windowState() | Qt.WindowState.WindowMaximized
        )
    return True

