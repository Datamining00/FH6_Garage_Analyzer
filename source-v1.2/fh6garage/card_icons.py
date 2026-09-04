from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap


ICON_SIZE = 20
ICON_FILES = {
    "move": "01_move.png", "zoom": "02_zoom.png",
    "memo": "03_memo.png", "memo_written": "04_memo_written.png",
    "info": "05_info.png", "folder": "06_folder.png",
    "export": "07_export.png", "paint": "08_paint.png",
    "unlock": "09_unlock.png", "lock": "10_lock.png",
    "visible": "11_visible.png", "hidden": "12_hidden.png",
    "circle": "13_circle.png", "triangle": "14_triangle.png",
    "excluded": "15_x.png", "import": "16_import.png",
    "collapse_right": "17_collapse_right.png",
    "expand_left": "18_expand_left.png",
}


def _icon_root() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "icons" / "cards"


def icon_path(kind: str) -> Path:
    return _icon_root() / ICON_FILES[kind]


@lru_cache(maxsize=128)
def _cached_pixmap(kind: str, color_name: str, size: int) -> QPixmap:
    source = QImage(str(icon_path(kind)))
    if source.isNull():
        return QPixmap()
    source = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    result = QPixmap.fromImage(source.convertToFormat(QImage.Format.Format_ARGB32))
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QColor(color_name))
    painter.end()
    return result


def pixmap(kind: str, color: QColor | str = "#555a68", size: int = ICON_SIZE) -> QPixmap:
    """Return an implicitly-shared pixmap without decoding the PNG per card."""
    normalized = QColor(color).name(QColor.NameFormat.HexArgb)
    return _cached_pixmap(kind, normalized, int(size))


@lru_cache(maxsize=128)
def _cached_icon(kind: str, color_name: str, size: int) -> QIcon:
    return QIcon(_cached_pixmap(kind, color_name, size))


def icon(kind: str, color: QColor | str = "#555a68", size: int = ICON_SIZE) -> QIcon:
    normalized = QColor(color).name(QColor.NameFormat.HexArgb)
    return _cached_icon(kind, normalized, int(size))


@lru_cache(maxsize=64)
def _cached_toggle_icon(off_kind: str, on_kind: str, off_color: str,
                        on_color: str, size: int) -> QIcon:
    result = QIcon()
    result.addPixmap(_cached_pixmap(off_kind, off_color, size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(_cached_pixmap(on_kind, on_color, size), QIcon.Mode.Normal, QIcon.State.On)
    return result


def toggle_icon(off_kind: str, on_kind: str | None = None, *,
                off_color: QColor | str = "#9ba5b3",
                on_color: QColor | str = "#6e4bf2", size: int = ICON_SIZE) -> QIcon:
    return _cached_toggle_icon(
        off_kind,
        on_kind or off_kind,
        QColor(off_color).name(QColor.NameFormat.HexArgb),
        QColor(on_color).name(QColor.NameFormat.HexArgb),
        int(size),
    )
