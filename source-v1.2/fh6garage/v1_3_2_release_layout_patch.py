from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QToolButton, QWidget


def _move_change_banner_to_reserved_slot(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    label = getattr(window, "refresh_diff_banner_label", None)
    view = getattr(window, "refresh_diff_view_button", None)
    slot = getattr(window, "_fh6_v132_reserved_backup_slot", None)
    if not isinstance(banner, QWidget) or not isinstance(slot, QWidget):
        return

    parent = banner.parentWidget()
    parent_layout = parent.layout() if isinstance(parent, QWidget) else None
    if parent_layout is not None:
        parent_layout.removeWidget(banner)

    slot_layout = slot.layout()
    if slot_layout is None:
        slot_layout = QHBoxLayout(slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.setSpacing(0)
    else:
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.setSpacing(0)

    banner.setParent(slot)
    banner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    banner.setStyleSheet(
        "QFrame#refreshDiffBanner { background:#eee9ff; border:1px solid #d8ceff; "
        "border-radius:8px; }"
    )
    inner = banner.layout()
    if inner is not None:
        inner.setContentsMargins(3, 2, 3, 2)
        inner.setSpacing(0)
        if inner.count() >= 3:
            inner.setStretch(0, 0)
            inner.setStretch(1, 0)
            inner.setStretch(2, 1)

    if label is not None:
        label.hide()
    if view is not None:
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        view.setStyleSheet(
            "QPushButton { background:transparent; color:#5538b6; border:0; "
            "padding:4px 2px; font-weight:700; }"
            "QPushButton:hover { background:#e6ddff; border-radius:6px; }"
        )
    slot_layout.addWidget(banner)


def _compact_change_banner(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    view = getattr(window, "refresh_diff_view_button", None)
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if banner is None or view is None:
        return
    if diff is None or getattr(diff, "baseline", False) or getattr(diff, "total", 0) <= 0:
        banner.hide()
        return

    added = len(getattr(diff, "added", []))
    removed = len(getattr(diff, "removed", []))
    changed = len(getattr(diff, "changed", []))
    view.setText(f"+{added}  −{removed}  ~{changed}")
    view.setToolTip(
        f"새로고침 변경 · 추가 {added} · 삭제 {removed} · 변경 {changed}\n클릭하여 보기"
    )
    banner.show()


def _align_left_actions_to_right_second_third(card: Any) -> None:
    if getattr(card, "_fh6_action_grid", None) is not None:
        return
    aligner = getattr(card, "_fh6_card_action_aligner", None)
    triangle = getattr(card, "_fh6_triangle_box", None)
    excluded = getattr(card, "_fh6_excluded_box", None)
    if aligner is None:
        return
    if not isinstance(triangle, QToolButton) or not isinstance(excluded, QToolButton):
        return

    # The legacy aligner calls these anchors fourth/fifth because it originally
    # targeted the zoom/memo rows. Repoint them to the right-side 2nd/3rd controls
    # (triangle / excluded) so hide and info share those exact centerlines.
    aligner.fourth_button = triangle
    aligner.fifth_button = excluded
    reposition = getattr(aligner, "reposition", None)
    if callable(reposition):
        QTimer.singleShot(0, reposition)


def apply_v1_3_2_release_layout_patch(MainWindow) -> None:
    """Finalize the compact refresh notice placement and refresh behavior."""
    if getattr(MainWindow, "_fh6_v132_release_layout_patched", False):
        return

    original_init = MainWindow.__init__
    original_populate_all = MainWindow._populate_all

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        _move_change_banner_to_reserved_slot(self)
        _compact_change_banner(self)

    def patched_populate_all(self) -> None:
        original_populate_all(self)
        _compact_change_banner(self)

    MainWindow.__init__ = patched_init
    MainWindow._populate_all = patched_populate_all
    MainWindow._fh6_v132_release_layout_patched = True
