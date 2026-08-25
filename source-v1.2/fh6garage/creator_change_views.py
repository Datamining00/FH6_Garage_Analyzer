from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from .creator_alias_views import decorate_creator_copy_label
from .i18n import get_language
from .models import LiveryRecord
from .refresh_history import LiverySnapshotEntry


def _txt(ko: str, en: str) -> str:
    return ko if get_language() == "ko" else en


def open_change_dialog(window: Any) -> None:
    from .change_dialog_responsive import _open_responsive_change_dialog

    _open_responsive_change_dialog(window)


def _find_current_livery(window: Any, entry: LiverySnapshotEntry | None) -> LiveryRecord | None:
    if entry is None or window.result is None:
        return None
    records = [record for record in window.result.liveries if record.kind == entry.kind]
    identity = entry.identity.casefold()
    for record in records:
        physical = f"{record.kind}:{record.container_name.casefold()}"
        if physical.casefold() == identity:
            return record

    guid = (entry.guid or "").strip().casefold()
    if guid:
        matches = [
            record for record in records
            if (record.header.guid or "").strip().casefold() == guid
        ]
        if len(matches) == 1:
            return matches[0]

    digest = (entry.content_sha256 or "").strip().casefold()
    if digest:
        matches = [
            record for record in records
            if (record.content_sha256 or "").strip().casefold() == digest
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _status_style(status: str) -> str:
    return {
        "added": "background:#e9f7ee;color:#237a43;border:1px solid #bfe6cc;",
        "removed": "background:#fff0f1;color:#b42d3a;border:1px solid #f0c4c8;",
        "changed": "background:#fff7e8;color:#8b5b0b;border:1px solid #efd5a5;",
    }.get(status, "background:#f1f2f6;color:#555a68;border:1px solid #dfe1e8;")


def _status_text(status: str) -> str:
    if status == "added":
        return _txt("+ 추가", "+ Added")
    if status == "removed":
        return _txt("− 삭제", "− Removed")
    return _txt("~ 변경", "~ Changed")


def _current_change_card(window: Any, entry: LiverySnapshotEntry) -> QWidget | None:
    record = _find_current_livery(window, entry)
    if record is None:
        return None
    key = window._content_annotation_key("livery", record)
    card = window._make_saved_content_card("livery", record, key)
    decorate_creator_copy_label(window, card, record.header.creator or "")
    try:
        window._load_livery_card_thumbnail(card)
    except Exception:
        pass
    return card


def initialize_change_view_ui(window: Any) -> None:
    banner = QFrame()
    banner.setObjectName("refreshDiffBanner")
    banner.setStyleSheet(
        "QFrame#refreshDiffBanner { background:#eee9ff;border:1px solid #d8ceff;"
        "border-radius:9px; }"
    )
    row = QHBoxLayout(banner)
    row.setContentsMargins(11, 7, 8, 7)
    label = QLabel()
    label.setStyleSheet("color:#4f35aa;font-weight:700;")
    view = QPushButton(_txt("보기", "View"))
    view.setObjectName("secondary")
    view.clicked.connect(lambda: open_change_dialog(window))
    row.addWidget(label)
    row.addStretch(1)
    row.addWidget(view)
    banner.hide()
    window.refresh_diff_banner = banner
    window.refresh_diff_banner_label = label
    window.refresh_diff_view_button = view

    central = window.centralWidget()
    root_layout = central.layout() if central is not None else None
    if root_layout is not None and root_layout.count() >= 2:
        content = root_layout.itemAt(1).widget()
        content_layout = content.layout() if content is not None else None
        if content_layout is not None:
            content_layout.insertWidget(1, banner)


def update_change_banner(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    label = getattr(window, "refresh_diff_banner_label", None)
    if banner is None or label is None:
        return
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or diff.baseline or diff.total <= 0:
        banner.hide()
        return
    label.setText(
        _txt(
            f"새로고침 변경 · 추가 {len(diff.added)} · 삭제 {len(diff.removed)} · 변경 {len(diff.changed)}",
            f"Refresh changes · Added {len(diff.added)} · Removed {len(diff.removed)} · Changed {len(diff.changed)}",
        )
    )
    banner.show()
