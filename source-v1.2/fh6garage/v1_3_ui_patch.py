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
GRID_TARGET_CARD_WIDTH = 420
GRID_MIN_COLUMNS = 2
GRID_MAX_COLUMNS = 4


def _language_icon_pixmap(size: int = 24) -> QPixmap:
    """Draw a high-contrast globe icon without relying on platform emoji fonts."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#b9a9ff"), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    rect = QRect(3, 3, size - 6, size - 6)
    painter.drawEllipse(rect)
    center_x = size // 2
    center_y = size // 2
    painter.drawLine(4, center_y, size - 4, center_y)
    painter.drawEllipse(QRect(center_x - 5, 3, 10, size - 6))
    painter.drawArc(QRect(3, center_y - 5, size - 6, 10), 0, 180 * 16)
    painter.drawArc(QRect(3, center_y - 5, size - 6, 10), 180 * 16, 180 * 16)
    painter.end()
    return pixmap


def _restart_button_text() -> str:
    return "재시작" if get_language() == "ko" else "Restart"


def _restart_failed_title() -> str:
    return "재시작 실패" if get_language() == "ko" else "Restart failed"


def _restart_failed_message() -> str:
    if get_language() == "ko":
        return "프로그램을 자동으로 다시 시작하지 못했습니다. 직접 다시 실행해 주세요."
    return "The application could not restart automatically. Please launch it again manually."


def _grid_column_count(self: Any, content_type: str) -> int:
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    if scroll is None or layout is None:
        return GRID_MIN_COLUMNS
    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return GRID_MIN_COLUMNS

    margins = layout.contentsMargins()
    inner_width = max(
        1,
        viewport.width() - margins.left() - margins.right() - 4,
    )
    columns = inner_width // GRID_TARGET_CARD_WIDTH
    return max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, int(columns)))


def apply_v1_3_ui_patches(MainWindow) -> None:
    """Apply v1.3 follow-up UI behavior before the first MainWindow is created."""
    if getattr(MainWindow, "_fh6_v13_followup_patched", False):
        return

    original_build_ui = MainWindow._build_ui
    original_layout_cards = MainWindow._layout_visible_grid_cards
    original_make_saved_content_card = MainWindow._make_saved_content_card
    original_set_always_on_top = MainWindow._set_always_on_top

    def patched_build_ui(self) -> None:
        original_build_ui(self)

        # Replace the low-visibility text label with a dedicated globe icon.
        language_label = getattr(self, "language_label", None)
        if isinstance(language_label, QLabel):
            language_label.setText("")
            language_label.setPixmap(_language_icon_pixmap(24))
            language_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            language_label.setToolTip(tr("language.label"))
            language_label.setAccessibleName(tr("language.label"))
            language_label.setFixedHeight(28)
            language_label.setStyleSheet("padding:0 6px;")

        # A language selection is only persisted immediately. The restart
        # button appears only when the persisted choice differs from this run's
        # active language, so users can change their mind without a forced restart.
        combo = getattr(self, "language_combo", None)
        if combo is not None:
            parent = combo.parentWidget()
            restart_button = QPushButton(_restart_button_text(), parent)
            restart_button.setObjectName("languageRestartButton")
            restart_button.setToolTip(tr("language.restart_required"))
            restart_button.setCursor(Qt.CursorShape.PointingHandCursor)
            restart_button.setStyleSheet(
                "QPushButton { background:#6e4bf2; color:white; border:0; "
                "border-radius:7px; padding:7px 8px; font-weight:600; }"
                "QPushButton:hover { background:#7c5cf4; }"
                "QPushButton:pressed { background:#5f3fdd; }"
            )
            restart_button.clicked.connect(self._restart_for_language_change)
            restart_button.hide()
            self.language_restart_button = restart_button

            parent_layout = parent.layout() if parent is not None else None
            if parent_layout is not None:
                combo_index = parent_layout.indexOf(combo)
                if combo_index >= 0:
                    parent_layout.insertWidget(combo_index + 1, restart_button)
                else:
                    parent_layout.addWidget(restart_button)

    def patched_language_changed(self, index: int) -> None:
        if index < 0:
            return
        raw_language = self.language_combo.itemData(index)
        if not isinstance(raw_language, str):
            return
        normalized = normalize_language(raw_language)
        self.settings.setValue("language", normalized)
        pending_restart = normalized != get_language()
        restart_button = getattr(self, "language_restart_button", None)
        if restart_button is not None:
            restart_button.setVisible(pending_restart)
        if pending_restart:
            self._show_status(tr("language.restart_required"), 6000)

    def restart_for_language_change(self) -> None:
        self.settings.sync()

        # A PyInstaller onefile restart must be a fresh top-level instance.
        # Otherwise PyInstaller 6.9+ may reuse the current _MEI directory,
        # which is removed as the old instance exits.
        frozen = bool(getattr(sys, "frozen", False))
        if frozen:
            program = sys.executable
            arguments = QApplication.arguments()[1:]
        else:
            program = sys.executable
            arguments = QApplication.arguments()

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
            QMessageBox.warning(
                self,
                _restart_failed_title(),
                _restart_failed_message(),
            )
            return
        QApplication.quit()

    def patched_set_always_on_top(
        self,
        enabled: bool,
        *,
        persist: bool = True,
    ) -> None:
        if persist:
            self.settings.setValue("window_always_on_top", enabled)

        # Qt's setWindowFlag() recreates/hides an already visible top-level
        # native window on Windows, which is the source of the visible flash.
        # SetWindowPos changes only the TOPMOST z-order state and leaves size,
        # position, visibility and activation untouched.
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                set_window_pos = user32.SetWindowPos
                set_window_pos.argtypes = [
                    wintypes.HWND,
                    wintypes.HWND,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    wintypes.UINT,
                ]
                set_window_pos.restype = wintypes.BOOL

                hwnd = wintypes.HWND(int(self.winId()))
                insert_after = wintypes.HWND(-1 if enabled else -2)
                flags = (
                    0x0001  # SWP_NOSIZE
                    | 0x0002  # SWP_NOMOVE
                    | 0x0010  # SWP_NOACTIVATE
                    | 0x0200  # SWP_NOOWNERZORDER
                    | 0x0400  # SWP_NOSENDCHANGING
                )
                if set_window_pos(hwnd, insert_after, 0, 0, 0, 0, flags):
                    return
            except (AttributeError, OSError, TypeError, ValueError):
                pass

        # Non-Windows fallback keeps the existing Qt behavior.
        original_set_always_on_top(self, enabled, persist=False)

    def patched_make_saved_content_card(self, content_type, record, key):
        card = original_make_saved_content_card(self, content_type, record, key)
        image_label = getattr(card, "_fh6_image_label", None)
        if image_label is not None:
            image_label.setMinimumHeight(IMAGE_MIN_HEIGHT)
        return card

    def patched_layout_visible_grid_cards(self, content_type: str, cards) -> None:
        columns = _grid_column_count(self, content_type)
        setattr(self, f"_fh6_{content_type}_grid_columns", columns)

        # Preserve the proven existing layout path at the normal two-column
        # width. Only the 3/4-column states need a generalized layout.
        if columns == 2:
            original_layout_cards(self, content_type, cards)
            return

        layout = getattr(self, f"{content_type}_grid_layout")
        vehicle_group_button = getattr(self, f"{content_type}_group_button")
        creator_group_button = getattr(
            self,
            f"{content_type}_creator_group_button",
        )
        group_by_vehicle = vehicle_group_button.isChecked()
        group_by_creator = creator_group_button.isChecked()

        if not group_by_vehicle and not group_by_creator:
            for index, card in enumerate(cards):
                layout.addWidget(card, index // columns, index % columns)
                card.setVisible(True)
            return

        if group_by_creator:
            key_property = "creatorGroupKey"
            label_property = "creatorGroupLabel"
            fallback_label = tr("creator.none")
        else:
            key_property = "vehicleGroupKey"
            label_property = "vehicleGroupLabel"
            fallback_label = "Unknown vehicle"

        grouped: dict[str, list] = {}
        labels: dict[str, str] = {}
        for card in cards:
            group_key = str(card.property(key_property) or "unknown")
            group_label = str(card.property(label_property) or fallback_label)
            grouped.setdefault(group_key, []).append(card)
            labels.setdefault(group_key, group_label)

        headers = (
            self._livery_group_headers
            if content_type == "livery"
            else self._tuning_group_headers
        )
        noun = (
            tr("content.noun_livery")
            if content_type == "livery"
            else tr("content.noun_tuning")
        )

        row = 0
        for group_key, group_cards in grouped.items():
            header = headers.get(group_key)
            if header is None:
                header = QLabel()
                header.setObjectName("vehicleGroupHeader")
                header.setStyleSheet(
                    "QLabel#vehicleGroupHeader { background:#eee9ff; color:#5335c7; "
                    "border:1px solid #d9d0ff; border-radius:8px; padding:9px 12px; "
                    "font-size:11pt; font-weight:700; }"
                )
                header.setMinimumHeight(38)
                headers[group_key] = header

            if group_by_creator:
                header.setText(
                    tr(
                        "content.creator_group_header",
                        creator=labels[group_key],
                        noun=noun,
                        count=len(group_cards),
                    )
                )
            else:
                header.setText(
                    tr(
                        "content.group_header",
                        vehicle=labels[group_key],
                        noun=noun,
                        count=len(group_cards),
                    )
                )

            layout.addWidget(header, row, 0, 1, columns)
            header.setVisible(True)
            row += 1
            for index, card in enumerate(group_cards):
                layout.addWidget(
                    card,
                    row + index // columns,
                    index % columns,
                )
                card.setVisible(True)
            row += (len(group_cards) + columns - 1) // columns

    MainWindow._build_ui = patched_build_ui
    MainWindow._on_language_preference_changed = patched_language_changed
    MainWindow._restart_for_language_change = restart_for_language_change
    MainWindow._set_always_on_top = patched_set_always_on_top
    MainWindow._make_saved_content_card = patched_make_saved_content_card
    MainWindow._layout_visible_grid_cards = patched_layout_visible_grid_cards
    MainWindow._fh6_grid_column_count = _grid_column_count
    MainWindow._fh6_v13_followup_patched = True
