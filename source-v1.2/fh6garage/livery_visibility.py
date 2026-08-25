from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QPushButton, QWidgetAction

from .models import LiveryRecord

HIDDEN_MODE = 11
AUCTION_APPLIED_MODE = 12
AUCTION_UNAPPLIED_MODE = 13
HIDDEN_PREFERENCE_PREFIX = "hidden_livery_v1_3_2:"


class BooleanPreferences(Protocol):
    def get_bool(self, key: str, default: bool = False) -> bool: ...

    def set_bool(self, key: str, value: bool) -> None: ...


def hidden_preference_key(content_key: str) -> str:
    return f"{HIDDEN_PREFERENCE_PREFIX}{content_key}"


def is_livery_hidden(preferences: BooleanPreferences, content_key: str) -> bool:
    return preferences.get_bool(hidden_preference_key(content_key), False)


def set_livery_hidden(
    preferences: BooleanPreferences,
    content_key: str,
    hidden: bool,
) -> None:
    preferences.set_bool(hidden_preference_key(content_key), bool(hidden))


def is_auction_livery_applied(record: object) -> bool:
    """Return whether a SoulBound record resolves to an existing cache image."""
    if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
        return False
    path = record.thumbnail_path
    try:
        return bool(path is not None and path.is_file())
    except OSError:
        return False


def eye_slash_pixmap(active: bool, size: int = 22) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#6e4bf2" if active else "#8d93a2"), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRect(3, 6, size - 6, size - 10), 15 * 16, 150 * 16)
    painter.drawArc(QRect(3, 6, size - 6, size - 10), 195 * 16, 150 * 16)
    painter.drawEllipse(QRect(size // 2 - 3, size // 2 - 3, 6, 6))
    painter.drawLine(4, 4, size - 4, size - 4)
    painter.end()
    return pixmap


def _cache_state_pixmap(applied: bool, size: int = 22) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#2e9b50" if applied else "#9aa0aa"), 1.8)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRect(3, 4, size - 6, size - 8), 3, 3)
    painter.drawLine(6, size - 7, 10, size - 11)
    painter.drawLine(10, size - 11, 13, size - 8)
    painter.drawLine(13, size - 8, size - 6, 7)
    if not applied:
        painter.drawLine(4, 4, size - 4, size - 4)
    painter.end()
    return pixmap


def install_visibility_filter_rows(button: object, labels: dict[str, str]) -> None:
    menu = button.menu()  # type: ignore[attr-defined]
    if menu is None:
        return
    menu.addSeparator()
    entries = (
        (HIDDEN_MODE, "hidden", "hidden_tip", QIcon(eye_slash_pixmap(True))),
        (AUCTION_UNAPPLIED_MODE, "auction_unapplied", "auction_unapplied_tip", QIcon(_cache_state_pixmap(False))),
    )
    for mode, label_key, tip_key, icon in entries:
        row = QPushButton(labels[label_key])
        row.setCheckable(True)
        row.setIcon(icon)
        row.setIconSize(QSize(22, 22))
        row.setToolTip(labels[tip_key])
        row.setFixedHeight(36)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            "QPushButton { background:transparent; color:#20232d; border:1px solid transparent; "
            "border-radius:6px; padding:5px 9px; text-align:left; }"
            "QPushButton:hover { background:#f4f1ff; border-color:#e5deff; }"
            "QPushButton:checked { background:#eee9ff; color:#5335c7; "
            "border-color:#d8ceff; font-weight:600; }"
        )
        row.toggled.connect(
            lambda checked=False, m=mode, owner=button: owner._row_toggled(m, checked)  # type: ignore[attr-defined]
        )
        action = QWidgetAction(menu)
        action.setDefaultWidget(row)
        menu.addAction(action)
        button._actions[mode] = row  # type: ignore[attr-defined]


def visibility_labels(korean: bool) -> dict[str, str]:
    pairs = {
        "hidden": ("숨김", "Hidden"),
        "hidden_tip": ("숨긴 리버리만 표시", "Show hidden liveries only"),
        "hide_toggle": ("이 리버리 숨기기", "Hide this livery"),
        "hidden_move": (
            "숨김 리버리는 이동 대상에서 제외됩니다.",
            "Hidden liveries are excluded from game movement.",
        ),
        "auction_applied": ("적용 경매장 리버리", "Applied auction livery"),
        "auction_applied_tip": (
            "CacheThumbnails manifest 등록 목록에서 확인된 SoulBound 리버리 (WebP 생성 여부와 무관)",
            "SoulBound liveries present in the CacheThumbnails manifest registry, regardless of WebP hydration",
        ),
        "auction_unapplied": ("미적용 경매장 리버리", "Unapplied auction livery"),
        "auction_unapplied_tip": (
            "CacheThumbnails manifest 등록 목록에서 확인되지 않은 SoulBound 리버리",
            "SoulBound liveries absent from the CacheThumbnails manifest registry",
        ),
    }
    index = 0 if korean else 1
    return {key: values[index] for key, values in pairs.items()}
