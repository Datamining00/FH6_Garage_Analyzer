from __future__ import annotations

import warnings
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QPushButton, QToolButton, QWidget

from . import v1_3_2_change_dialog_folder_patch as _feature


def _repair_change_button(window: Any) -> None:
    """Restore mouse input to the compact refresh-change button.

    The reserved toolbar slot was intentionally created with
    WA_TransparentForMouseEvents while it was empty. Once the change banner is
    reparented into that slot the attribute must be disabled, otherwise the
    visible +/−/~ button cannot receive mouse input.
    """
    slot = getattr(window, "_fh6_v132_reserved_backup_slot", None)
    banner = getattr(window, "refresh_diff_banner", None)
    view = getattr(window, "refresh_diff_view_button", None)

    if isinstance(slot, QWidget):
        slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        slot.setEnabled(True)
    if isinstance(banner, QWidget):
        banner.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        banner.setEnabled(True)
    if not isinstance(view, QPushButton):
        return

    view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    view.setEnabled(True)
    try:
        # PySide emits a RuntimeWarning before raising when disconnect() has no
        # matching connection. That condition is harmless here: the goal is to
        # clear any legacy handler before installing the current one.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            view.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass
    view.clicked.connect(
        lambda _checked=False, owner=window:
        _feature._open_change_dialog_same_as_main(owner)
    )


def _repoint_legacy_aligners(card: Any) -> None:
    """Make every historical aligner agree with the new four-row contract.

    v1.3.2 accumulated more than one event-filter based card aligner. Leaving
    an older hide aligner pointed at the zoom row makes it race the new aligner
    and can cover the folder button. Repointing the existing aligners avoids
    competing geometry rather than adding another independent layout owner.
    """
    triangle = getattr(card, "_fh6_triangle_box", None)
    excluded = getattr(card, "_fh6_excluded_box", None)

    hide_aligner = getattr(card, "_fh6_hide_aligner", None)
    if hide_aligner is not None and isinstance(triangle, QToolButton):
        if hasattr(hide_aligner, "target_button"):
            hide_aligner.target_button = triangle

    card_aligner = getattr(card, "_fh6_card_action_aligner", None)
    if card_aligner is not None:
        if isinstance(triangle, QToolButton) and hasattr(card_aligner, "fourth_button"):
            card_aligner.fourth_button = triangle
        if isinstance(excluded, QToolButton) and hasattr(card_aligner, "fifth_button"):
            card_aligner.fifth_button = excluded


def _force_card_action_geometry(card: Any) -> None:
    """Run all retained aligners in a deterministic order, four-row owner last."""
    for name in (
        "_fh6_hide_aligner",
        "_fh6_card_action_aligner",
        "_fh6_four_left_action_aligner",
    ):
        aligner = getattr(card, name, None)
        reposition = getattr(aligner, "reposition", None)
        if callable(reposition):
            reposition()


def _repair_card_actions(card: Any, record: Any) -> None:
    if bool(card.property("fh6ArchiveCard")):
        return

    # Retained for compatibility with older partial patch stacks. The current
    # v1.4 runtime no longer installs this as a card-construction wrapper;
    # folder/action creation is owned by the preceding folder patch and final
    # geometry is owned by v1.3.4 card_action_layout.
    _feature._install_four_left_actions(card, record)
    if getattr(card, "_fh6_action_grid", None) is not None:
        return
    _repoint_legacy_aligners(card)

    _force_card_action_geometry(card)
    QTimer.singleShot(0, lambda c=card: _force_card_action_geometry(c))
    QTimer.singleShot(50, lambda c=card: _force_card_action_geometry(c))


def apply_v1_3_2_change_dialog_runtime_fix(MainWindow) -> None:
    """Keep only the still-active compact change-button runtime correction."""
    if getattr(MainWindow, "_fh6_v132_change_dialog_runtime_fixed", False):
        return

    original_init = MainWindow.__init__

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        _repair_change_button(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v132_change_dialog_runtime_fixed = True
