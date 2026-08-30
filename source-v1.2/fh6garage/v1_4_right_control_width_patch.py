from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QPushButton, QSizePolicy, QToolButton

from .i18n import tr


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
    # The user-visible Export button is the canonical width. sizeHint is stable
    # before/after native layout and therefore avoids startup timing differences.
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

    # The recent-change counters have a transparent frame around the visible
    # button. Fix both layers so 0/10/100 values cannot change outer geometry.
    banner = getattr(window, "refresh_diff_banner", None)
    counter = getattr(window, "refresh_diff_view_button", None)
    if isinstance(banner, QFrame):
        banner.setMinimumWidth(width)
        banner.setMaximumWidth(width)
        banner.setFixedWidth(width)
        banner.setSizePolicy(QSizePolicy.Policy.Fixed, banner.sizePolicy().verticalPolicy())
    _set_fixed_control_width(counter, width)


def apply_v1_4_right_control_width_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_right_control_width_patched", False):
        return

    original_init = MainWindow.__init__
    original_show_event = MainWindow.showEvent
    original_resize_event = MainWindow.resizeEvent

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _sync_right_control_widths(self)

    def patched_show_event(self: Any, event: Any) -> None:
        original_show_event(self, event)
        # Runs after the display-row geometry patch, so its intrinsic counter
        # width cannot overwrite the shared Export-based width.
        _sync_right_control_widths(self)

    def patched_resize_event(self: Any, event: Any) -> None:
        original_resize_event(self, event)
        _sync_right_control_widths(self)

    MainWindow.__init__ = patched_init
    MainWindow.showEvent = patched_show_event
    MainWindow.resizeEvent = patched_resize_event
    MainWindow._fh6_v14_right_control_width_patched = True
