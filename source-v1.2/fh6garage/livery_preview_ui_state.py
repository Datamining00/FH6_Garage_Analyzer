from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage, QTransform

VIEW_MODE_SETTING_KEY = "livery_preview_view_mode"
DEFAULT_VIEW_MODE = "fit"

SECTION_DISPLAY_ROTATION_DEGREES = {
    "Right": 180,
    "RightWindow": 180,
    "FrontWindshield": -90,
    "BackWindshield": 90,
}


def normalize_view_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_VIEW_MODE).strip().lower()
    return mode if mode in {"fit", "actual"} else DEFAULT_VIEW_MODE


def load_view_mode(settings: QSettings) -> str:
    return normalize_view_mode(settings.value(VIEW_MODE_SETTING_KEY, DEFAULT_VIEW_MODE, str))


def save_view_mode(settings: QSettings, mode: str) -> str:
    normalized = normalize_view_mode(mode)
    settings.setValue(VIEW_MODE_SETTING_KEY, normalized)
    settings.sync()
    return normalized


def rotate_section_image(image: QImage, section: str) -> QImage:
    angle = int(SECTION_DISPLAY_ROTATION_DEGREES.get(str(section), 0))
    if image.isNull() or not angle:
        return image
    transform = QTransform()
    transform.rotate(angle)
    return image.transformed(transform)
