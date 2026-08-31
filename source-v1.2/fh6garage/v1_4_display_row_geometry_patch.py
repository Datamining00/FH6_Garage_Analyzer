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


def _pin_pair_after_trailing_stretch(
    layout: QHBoxLayout,
    left_widget: Any,
    right_widget: Any,
) -> None:
    """Place two terminal widgets after the row's existing stretch item.

    Search has an expanding field followed by Filter. The display row is made
    geometrically equivalent by keeping No-applied immediately before the recent
    counter, with both widgets after the flexible stretch. When Filter and the
    recent counter share one width, the search-field right edge and the
    No-applied right edge therefore share the same X coordinate.
    """
    if left_widget is None or right_widget is None:
        return
    if layout.indexOf(left_widget) < 0 or layout.indexOf(right_widget) < 0:
        return
    layout.removeWidget(left_widget)
    layout.removeWidget(right_widget)
    layout.addWidget(left_widget)
    layout.addWidget(right_widget)


def _pin_widget_after_trailing_stretch(layout: QHBoxLayout, widget: Any) -> None:
    if widget is None or layout.indexOf(widget) < 0:
        return
    if layout.indexOf(widget) == layout.count() - 1:
        return
    layout.removeWidget(widget)
    layout.addWidget(widget)


def _sync_display_row_geometry(window: Any) -> None:
    """Own only structural placement; width is owned by the shared-width patch.

    The recent counter deliberately has no intrinsic/fallback width here. It is
    laid out exactly like Export: terminal control after a flexible stretch, and
    v1_4_right_control_width_patch applies the single Export-derived width.
    """
    if bool(getattr(window, "_fh6_syncing_recent_geometry", False)):
        return
    window._fh6_syncing_recent_geometry = True
    try:
        banner = getattr(window, "refresh_diff_banner", None)
        export = getattr(window, "livery_export_visible_button", None)
        no_applied = getattr(window, "livery_no_applied_toggle", None)
        search_row, display_row, action_row = _livery_control_rows(window)
        if (
            not isinstance(banner, QFrame)
            or not isinstance(export, QPushButton)
            or not isinstance(no_applied, QPushButton)
            or not isinstance(search_row, QHBoxLayout)
            or not isinstance(display_row, QHBoxLayout)
            or not isinstance(action_row, QHBoxLayout)
        ):
            return

        # Use one inter-control gap for the right-hand column across all three
        # livery toolbar rows. This makes the expanding search field naturally
        # consume the small residual width needed to align with No-applied.
        search_row.setSpacing(_RIGHT_COLUMN_GAP)
        display_row.setSpacing(_RIGHT_COLUMN_GAP)
        action_row.setSpacing(_RIGHT_COLUMN_GAP)

        # Display row: ... stretch | No applied | recent counts
        _pin_pair_after_trailing_stretch(display_row, no_applied, banner)
        # Action row: ... stretch | Export
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
