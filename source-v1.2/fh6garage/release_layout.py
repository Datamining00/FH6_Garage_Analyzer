from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget


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
    slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    slot.setEnabled(True)
    banner.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    banner.setEnabled(True)
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
        view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        view.setEnabled(True)
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
