from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton

from . import v1_4_ui_completion_patch as _ui


_RIGHT_COLUMN_GAP = 7


def _livery_control_rows(window: Any) -> tuple[QHBoxLayout | None, QHBoxLayout | None, QHBoxLayout | None]:
    """Return search, display and action rows for the livery page."""
    pages = getattr(window, "pages", None)
    if pages is None:
        return None, None, None
    try:
        page = pages.widget(1)
    except Exception:
        return None, None, None
    root = page.layout() if page is not None else None
    controls_item = root.itemAt(1) if root is not None and root.count() > 1 else None
    controls = controls_item.layout() if controls_item is not None else None
    search_item = controls.itemAt(0) if controls is not None and controls.count() > 0 else None
    display_item = controls.itemAt(1) if controls is not None and controls.count() > 1 else None
    search_row = search_item.layout() if search_item is not None else None
    display_row = display_item.layout() if display_item is not None else None
    action_row = getattr(window, "_saved_content_action_rows", {}).get("livery")
    return (
        search_row if isinstance(search_row, QHBoxLayout) else None,
        display_row if isinstance(display_row, QHBoxLayout) else None,
        action_row if isinstance(action_row, QHBoxLayout) else None,
    )


def _pin_widget_after_trailing_stretch(layout: QHBoxLayout, widget: Any) -> None:
    """Keep one terminal control after the row's trailing stretch."""
    if widget is None or layout.indexOf(widget) < 0:
        return
    if layout.indexOf(widget) == layout.count() - 1:
        return
    layout.removeWidget(widget)
    layout.addWidget(widget)


def _sync_display_row_geometry(window: Any) -> None:
    """Own structural placement only; shared-width patch owns control widths.

    Keep the native status-filter order intact. In particular,
    ``적용된 리버리 없음`` remains directly after ``미적용 리버리`` as installed
    by the status-filter patch. Only the recent counter is treated as the
    right-terminal control, matching Export's placement rule.
    """
    if bool(getattr(window, "_fh6_syncing_recent_geometry", False)):
        return
    window._fh6_syncing_recent_geometry = True
    try:
        banner = getattr(window, "refresh_diff_banner", None)
        export = getattr(window, "livery_export_visible_button", None)
        search_row, display_row, action_row = _livery_control_rows(window)
        if (
            not isinstance(banner, QFrame)
            or not isinstance(export, QPushButton)
            or not isinstance(search_row, QHBoxLayout)
            or not isinstance(display_row, QHBoxLayout)
            or not isinstance(action_row, QHBoxLayout)
        ):
            return

        # Keep a consistent toolbar gap, but do not reposition native filter
        # buttons. The search field therefore keeps its normal expanding policy.
        search_row.setSpacing(_RIGHT_COLUMN_GAP)
        display_row.setSpacing(_RIGHT_COLUMN_GAP)
        action_row.setSpacing(_RIGHT_COLUMN_GAP)

        # Display row: native filters ... | stretch | recent counts
        # Action row:  native actions  ... | stretch | Export
        _pin_widget_after_trailing_stretch(display_row, banner)
        _pin_widget_after_trailing_stretch(action_row, export)

        search_row.invalidate()
        display_row.invalidate()
        action_row.invalidate()
        search_row.activate()
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
    # They now re-assert structure only; the later shared-width patch owns every
    # actual right-column width, including the recent counter.
    _ui._sync_recent_change_banner_width = _sync_display_row_geometry
    MainWindow.__init__ = patched_init
    MainWindow.showEvent = patched_show_event
    MainWindow.resizeEvent = patched_resize_event
    MainWindow._fh6_v14_display_row_geometry_patched = True
