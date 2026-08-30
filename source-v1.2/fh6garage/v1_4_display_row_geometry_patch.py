from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from . import v1_4_ui_completion_patch as _ui


def _intrinsic_recent_width(window: Any) -> int:
    view = getattr(window, "refresh_diff_view_button", None)
    if not isinstance(view, QPushButton):
        return 96
    labels = _ui._ensure_recent_number_labels(view)
    layout = view.layout()
    if layout is not None:
        layout.activate()
    label_width = sum(max(18, label.sizeHint().width()) for label in labels)
    spacing = layout.spacing() if layout is not None else 4
    margins = layout.contentsMargins() if layout is not None else None
    margin_width = (margins.left() + margins.right()) if margins is not None else 16
    calculated = label_width + spacing * 2 + margin_width
    return max(96, calculated)


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
    if bool(getattr(window, "_fh6_syncing_recent_geometry", False)):
        return
    window._fh6_syncing_recent_geometry = True
    try:
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

        _protect_display_button_widths(window)
        root = page.layout()
        if root is not None:
            root.activate()
        row.activate()

        banner_left = banner.mapTo(page, QPoint(0, 0)).x()
        export_right = export.mapTo(page, QPoint(export.width(), 0)).x()
        target = export_right - banner_left
        if target <= 0:
            target = _intrinsic_recent_width(window)

        # The visible border belongs to the inner button, not the transparent
        # banner frame. Give both the exact same width so the border's right X
        # matches Export. Counter text size never changes this outer geometry.
        target = max(96, target)
        banner.setFixedWidth(target)
        view.setMinimumWidth(0)
        view.setMaximumWidth(target)
        view.setFixedWidth(target)
        view.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        row.invalidate()
        row.activate()
    finally:
        window._fh6_syncing_recent_geometry = False


class _RightEdgeObserver(QObject):
    """Resync when the Export button receives its final native geometry."""

    def __init__(self, window: Any, watched: QWidget) -> None:
        super().__init__(window)
        self.window = window
        watched.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in {QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show}:
            _sync_display_row_geometry(self.window)
        return False


def _install_right_edge_observer(window: Any) -> None:
    export = getattr(window, "livery_export_visible_button", None)
    if not isinstance(export, QPushButton):
        return
    if isinstance(getattr(window, "_fh6_recent_edge_observer", None), _RightEdgeObserver):
        return
    window._fh6_recent_edge_observer = _RightEdgeObserver(window, export)


def apply_v1_4_display_row_geometry_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_display_row_geometry_patched", False):
        return

    original_init = MainWindow.__init__
    original_show_event = MainWindow.showEvent
    original_resize_event = MainWindow.resizeEvent

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _install_right_edge_observer(self)
        _sync_display_row_geometry(self)

    def patched_show_event(self: Any, event: Any) -> None:
        original_show_event(self, event)
        _sync_display_row_geometry(self)

    def patched_resize_event(self: Any, event: Any) -> None:
        original_resize_event(self, event)
        _sync_display_row_geometry(self)

    # Existing completion-layer callbacks resolve this module global at execution
    # time. The observer also catches later Export geometry changes, so the final
    # right edge is not dependent on a guessed delay or on counter text width.
    _ui._sync_recent_change_banner_width = _sync_display_row_geometry
    MainWindow.__init__ = patched_init
    MainWindow.showEvent = patched_show_event
    MainWindow.resizeEvent = patched_resize_event
    MainWindow._fh6_v14_display_row_geometry_patched = True
