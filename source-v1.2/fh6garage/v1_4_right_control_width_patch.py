from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QPushButton, QSizePolicy, QToolButton

from .i18n import tr
from . import v1_4_display_row_geometry_patch as _geometry
from . import v1_4_ui_completion_patch as _ui


def _global_refresh_button(window: Any) -> QPushButton | None:
    """Find the single top-level full refresh button without changing base UI."""
    expected = tr("save.refresh")
    for button in window.findChildren(QPushButton):
        if button.text() == expected:
            return button
    return None


def _reference_width(window: Any) -> int | None:
    export = getattr(window, "livery_export_visible_button", None)
    if not isinstance(export, QPushButton):
        return None
    # Export is the canonical visible width. Its intrinsic size hint is stable
    # even after setFixedWidth(), so every tab uses one deterministic reference.
    return max(1, int(export.sizeHint().width()))


def _set_fixed_control_width(widget: Any, width: int) -> None:
    if not isinstance(widget, (QPushButton, QToolButton)):
        return
    widget.setMinimumWidth(width)
    widget.setMaximumWidth(width)
    widget.setFixedWidth(width)
    widget.setSizePolicy(QSizePolicy.Policy.Fixed, widget.sizePolicy().verticalPolicy())


def _sync_right_control_widths(window: Any) -> None:
    width = _reference_width(window)
    if width is None:
        return
    window._fh6_right_control_reference_width = width

    refresh = _global_refresh_button(window)
    targets = (
        # Shared top-right control used on Livery, Tuning, and Backup pages.
        refresh,
        # Livery page.
        getattr(window, "livery_check_filter", None),
        getattr(window, "livery_export_visible_button", None),
        # Tuning page.
        getattr(window, "tuning_check_filter", None),
        # Backup page.
        getattr(window, "backup_refresh_button", None),
        getattr(window, "backup_filter_button", None),
    )
    for widget in targets:
        _set_fixed_control_width(widget, width)

    # The recent-change control has a transparent wrapper and a visible inner
    # QPushButton. They must both own exactly the Export reference width.
    banner = getattr(window, "refresh_diff_banner", None)
    counter = getattr(window, "refresh_diff_view_button", None)
    if isinstance(banner, QFrame):
        banner.setMinimumWidth(width)
        banner.setMaximumWidth(width)
        banner.setFixedWidth(width)
        banner.setSizePolicy(QSizePolicy.Policy.Fixed, banner.sizePolicy().verticalPolicy())
    _set_fixed_control_width(counter, width)


def _sync_right_geometry_and_widths(window: Any) -> None:
    """Apply structural right anchoring first, then the shared Export width.

    v1_4_ui_completion_patch schedules deferred calls through
    _sync_recent_change_banner_width after population/relayout. If those calls
    target only the geometry patch, its intrinsic 96px counter width overwrites
    the shared width later. This combined callback makes every deferred path end
    with the Export-based width instead.
    """
    _geometry._sync_display_row_geometry(window)
    _sync_right_control_widths(window)


def apply_v1_4_right_control_width_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_right_control_width_patched", False):
        return

    original_init = MainWindow.__init__
    original_show_event = MainWindow.showEvent
    original_resize_event = MainWindow.resizeEvent

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _sync_right_geometry_and_widths(self)

    def patched_show_event(self: Any, event: Any) -> None:
        original_show_event(self, event)
        _sync_right_geometry_and_widths(self)

    def patched_resize_event(self: Any, event: Any) -> None:
        original_resize_event(self, event)
        _sync_right_geometry_and_widths(self)

    # Crucial: UI-completion has delayed singleShot callbacks that resolve this
    # module global at execution time. Own that final callback here so no later
    # population/relayout can restore the counter's old intrinsic 96px width.
    _ui._sync_recent_change_banner_width = _sync_right_geometry_and_widths

    MainWindow.__init__ = patched_init
    MainWindow.showEvent = patched_show_event
    MainWindow.resizeEvent = patched_resize_event
    MainWindow._fh6_v14_right_control_width_patched = True
