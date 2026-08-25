from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from typing import Any

from PySide6.QtCore import QProcess, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

from .i18n import get_language, normalize_language, tr

IMAGE_MIN_HEIGHT = 260


def _language_icon_pixmap(size: int = 24) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#b9a9ff"), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    rect = QRect(3, 3, size - 6, size - 6)
    center_x = size // 2
    center_y = size // 2
    painter.drawEllipse(rect)
    painter.drawLine(4, center_y, size - 4, center_y)
    painter.drawEllipse(QRect(center_x - 5, 3, 10, size - 6))
    painter.drawArc(QRect(3, center_y - 5, size - 6, 10), 0, 180 * 16)
    painter.drawArc(QRect(3, center_y - 5, size - 6, 10), 180 * 16, 180 * 16)
    painter.end()
    return pixmap


def configure_language_controls(owner: Any) -> None:
    label = getattr(owner, "language_label", None)
    if isinstance(label, QLabel):
        label.setText("")
        label.setPixmap(_language_icon_pixmap(24))
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setToolTip(tr("language.label"))
        label.setAccessibleName(tr("language.label"))
        label.setFixedHeight(28)
        label.setStyleSheet("padding:0 6px;")
    combo = getattr(owner, "language_combo", None)
    if combo is None or getattr(owner, "language_restart_button", None) is not None:
        return
    parent = combo.parentWidget()
    button = QPushButton("재시작" if get_language() == "ko" else "Restart", parent)
    button.setObjectName("languageRestartButton")
    button.setToolTip(tr("language.restart_required"))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        "QPushButton { background:#6e4bf2; color:white; border:0; "
        "border-radius:7px; padding:7px 8px; font-weight:600; }"
        "QPushButton:hover { background:#7c5cf4; }"
        "QPushButton:pressed { background:#5f3fdd; }"
    )
    button.clicked.connect(owner._restart_for_language_change)
    button.hide()
    owner.language_restart_button = button
    layout = parent.layout() if parent is not None else None
    if layout is not None:
        index = layout.indexOf(combo)
        if index >= 0:
            layout.insertWidget(index + 1, button)
        else:
            layout.addWidget(button)


def persist_language_preference(owner: Any, index: int) -> None:
    if index < 0:
        return
    raw = owner.language_combo.itemData(index)
    if not isinstance(raw, str):
        return
    normalized = normalize_language(raw)
    owner.settings.setValue("language", normalized)
    pending = normalized != get_language()
    button = getattr(owner, "language_restart_button", None)
    if button is not None:
        button.setVisible(pending)
    if pending:
        owner._show_status(tr("language.restart_required"), 6000)


def restart_application(owner: Any) -> None:
    owner.settings.sync()
    frozen = bool(getattr(sys, "frozen", False))
    program = sys.executable
    arguments = QApplication.arguments()[1:] if frozen else QApplication.arguments()
    reset_key = "PYINSTALLER_RESET_ENVIRONMENT"
    previous_reset = os.environ.get(reset_key)
    if frozen:
        os.environ[reset_key] = "1"
    try:
        result = QProcess.startDetached(program, arguments)
    finally:
        if frozen:
            if previous_reset is None:
                os.environ.pop(reset_key, None)
            else:
                os.environ[reset_key] = previous_reset
    started = result[0] if isinstance(result, tuple) else bool(result)
    if not started:
        title = "재시작 실패" if get_language() == "ko" else "Restart failed"
        message = "프로그램을 자동으로 다시 시작하지 못했습니다. 직접 다시 실행해 주세요." if get_language() == "ko" else "The application could not restart automatically. Please launch it again manually."
        QMessageBox.warning(owner, title, message)
        return
    QApplication.quit()


def set_always_on_top(owner: Any, enabled: bool, *, persist: bool = True) -> None:
    if persist:
        owner.settings.setValue("window_always_on_top", enabled)
    if sys.platform == "win32":
        try:
            set_window_pos = ctypes.windll.user32.SetWindowPos
            set_window_pos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            set_window_pos.restype = wintypes.BOOL
            flags = 0x0001 | 0x0002 | 0x0010 | 0x0200 | 0x0400
            if set_window_pos(wintypes.HWND(int(owner.winId())), wintypes.HWND(-1 if enabled else -2), 0, 0, 0, 0, flags):
                return
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    was_visible = owner.isVisible()
    was_maximized = owner.isMaximized()
    owner.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
    if was_visible:
        owner.showMaximized() if was_maximized else owner.show()
