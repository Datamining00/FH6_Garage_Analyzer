from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from . import v1_4_ui_completion_patch as _ui


def _intrinsic_recent_width(window: Any) -> int:
    view = getattr(window, "refresh_diff_view_button", None)
    if not isinstance(view, QPushButton):
        return 96
    labels = _ui._ensure_recent_number_labels(view)
    layout = view.layout()
    if layout is not None:
        layout.activate()
    label_width = sum(max(16, label.sizeHint().width()) for label in labels)
    spacing = layout.spacing() if layout is not None else 14
    margins = layout.contentsMargins() if layout is not None else None
    margin_width = (margins.left() + margins.right()) if margins is not None else 20
    calculated = label_width + spacing * 2 + margin_width
    return max(96, calculated, view.sizeHint().width())


def _protect_display_button_widths(window: Any) -> None:
    row = _ui._recent_display_row(window)
    banner = getattr(window, "refresh_diff_banner", None)
    if not isinstance(row, QHBoxLayout):
        return
    for index in range(row.count()):
        item = row.itemAt(index)
        widget = item.widget() if item is not None else None
        if not isinstance(widget, QPushButton):
            continue
        if widget is banner:
            continue
        widget.setMinimumWidth(widget.sizeHint().width())


def _sync_display_row_geometry(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    view = getattr(window, "refresh_diff_view_button", None)
    export = getattr(window, "livery_export_visible_button", None)
    pages = getattr(window, "pages", None)
    row = _ui._recent_display_row(window)
    if (
        not isinstance(banner, QFrame)
        or not isinstance(view, QPushButton)
        or not isinstance(export, QPushButton)
        or pages is None
        or not isinstance(row, QHBoxLayout)
    ):
        return

    try:
        page = pages.widget(1)
    except Exception:
        return
    if not isinstance(page, QWidget):
        return

    intrinsic = _intrinsic_recent_width(window)
    view.setMinimumWidth(intrinsic)
    banner.setMinimumWidth(intrinsic)
    _protect_display_button_widths(window)

    root = page.layout()
    if root is not None:
        root.activate()
    row.activate()

    banner_left = banner.mapTo(page, QPoint(0, 0)).x()
    export_right = export.mapTo(page, QPoint(export.width(), 0)).x()
    target = max(intrinsic, export_right - banner_left)

    # Never let right-edge synchronization steal width from the display filters.
    # If the page geometry is not final yet, the intrinsic 0/0/0 width is enough
    # for the first paint; show/resize events will re-run this with final geometry.
    if page.width() > 0 and 0 <= banner_left < page.width():
        target = min(target, max(intrinsic, page.width() - banner_left))
    banner.setFixedWidth(target)
    row.invalidate()
    row.activate()


def apply_v1_4_display_row_geometry_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_display_row_geometry_patched", False):
        return

    original_init = MainWindow.__init__
    original_show_event = MainWindow.showEvent
    original_resize_event = MainWindow.resizeEvent

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _sync_display_row_geometry(self)

    def patched_show_event(self: Any, event: Any) -> None:
        original_show_event(self, event)
        _sync_display_row_geometry(self)

    def patched_resize_event(self: Any, event: Any) -> None:
        original_resize_event(self, event)
        _sync_display_row_geometry(self)

    # Existing completion-layer deferred callbacks resolve this module global at
    # execution time. Replacing it makes them use the same safe calculation, but
    # correctness no longer depends on a timer: init/show/resize are synchronous.
    _ui._sync_recent_change_banner_width = _sync_display_row_geometry
    MainWindow.__init__ = patched_init
    MainWindow.showEvent = patched_show_event
    MainWindow.resizeEvent = patched_resize_event
    MainWindow._fh6_v14_display_row_geometry_patched = True
