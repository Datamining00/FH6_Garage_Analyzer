from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QSizePolicy

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
    if not isinstance(row, QHBoxLayout):
        return
    for index in range(row.count()):
        item = row.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QPushButton):
            widget.setMinimumWidth(widget.sizeHint().width())


def _pin_widget_after_trailing_stretch(layout: QHBoxLayout, widget: Any) -> None:
    """Put a terminal control after the row's stretch so Qt owns right alignment.

    Both the display row and the action row are sibling layouts inside the same
    controls VBox. Keeping their terminal widgets after their respective stretch
    items makes both right borders use the same layout content edge. No mapped
    coordinates, guessed widths, resize observers, or deferred correction are
    required.
    """
    if widget is None or layout.indexOf(widget) < 0:
        return
    if layout.indexOf(widget) == layout.count() - 1:
        return
    layout.removeWidget(widget)
    layout.addWidget(widget)


def _sync_display_row_geometry(window: Any) -> None:
    if bool(getattr(window, "_fh6_syncing_recent_geometry", False)):
        return
    window._fh6_syncing_recent_geometry = True
    try:
        banner = getattr(window, "refresh_diff_banner", None)
        view = getattr(window, "refresh_diff_view_button", None)
        export = getattr(window, "livery_export_visible_button", None)
        display_row = _ui._recent_display_row(window)
        action_row = getattr(window, "_saved_content_action_rows", {}).get("livery")
        if (
            not isinstance(banner, QFrame)
            or not isinstance(view, QPushButton)
            or not isinstance(export, QPushButton)
            or not isinstance(display_row, QHBoxLayout)
            or not isinstance(action_row, QHBoxLayout)
        ):
            return

        # Structural alignment: the flexible stretch is before each terminal
        # control, so both visible right borders terminate at the same content X.
        _pin_widget_after_trailing_stretch(display_row, banner)
        _pin_widget_after_trailing_stretch(action_row, export)

        intrinsic = _intrinsic_recent_width(window)
        banner.setFixedWidth(intrinsic)
        view.setFixedWidth(intrinsic)
        view.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        _protect_display_button_widths(window)

        display_row.invalidate()
        action_row.invalidate()
        display_row.activate()
        action_row.activate()
    finally:
        window._fh6_syncing_recent_geometry = False


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

    # Older completion-layer callbacks resolve this global at execution time.
    # They now re-assert the structural right anchor rather than calculate X
    # coordinates, so later population/layout work cannot reintroduce drift.
    _ui._sync_recent_change_banner_width = _sync_display_row_geometry
    MainWindow.__init__ = patched_init
    MainWindow.showEvent = patched_show_event
    MainWindow.resizeEvent = patched_resize_event
    MainWindow._fh6_v14_display_row_geometry_patched = True
