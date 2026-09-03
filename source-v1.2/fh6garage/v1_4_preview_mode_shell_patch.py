from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import get_language, tr
from .models import LiveryRecord
from .ui import APP_STYLE, ZoomableImageView


def _txt(ko: str, en: str) -> str:
    return ko if get_language().casefold().startswith("ko") else en


def _show_livery_preview_shell(window: Any, record: LiveryRecord) -> None:
    """Stage-1 preview shell.

    This intentionally contains no 3D backend import.  The existing image
    viewer remains the initial/default page; the 3D page is a passive UI shell
    used to validate integration and packaging before any OpenGL work is added.
    """
    path = record.thumbnail_path
    if not path or not path.is_file():
        QMessageBox.information(window, tr("image.none_title"), tr("image.none_message"))
        return

    try:
        image = QImage.fromData(path.read_bytes())
    except OSError as exc:
        QMessageBox.warning(window, tr("image.read_failed"), str(exc))
        return

    if image.isNull():
        QMessageBox.warning(window, tr("image.read_failed"), tr("image.format_failed"))
        return

    dialog = QDialog(window)
    livery_name = record.header.name or "(unnamed)"
    car_name = window._car_label(record.header.car_id)
    dialog.setWindowTitle(f"{livery_name} — {car_name}")
    dialog.setModal(True)
    dialog.setStyleSheet(APP_STYLE + "QDialog { background:#f7f8fb; }")

    available = window.screen().availableGeometry()
    target_w = max(900, min(1500, int(available.width() * 0.92)))
    target_h = max(620, min(960, int(available.height() * 0.90)))
    dialog.resize(target_w, target_h)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    stack = QStackedWidget()
    viewer = ZoomableImageView(QPixmap.fromImage(image))
    stack.addWidget(viewer)

    three_d_page = QWidget()
    three_d_layout = QVBoxLayout(three_d_page)
    three_d_layout.setContentsMargins(12, 12, 12, 12)
    three_d_message = QLabel(
        _txt(
            "3D 백엔드는 다음 검증 단계에서 연결됩니다.",
            "The 3D backend will be connected in the next validated stage.",
        )
    )
    three_d_message.setObjectName("muted")
    three_d_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
    three_d_message.setWordWrap(True)
    three_d_layout.addStretch(1)
    three_d_layout.addWidget(three_d_message)
    three_d_layout.addStretch(1)
    stack.addWidget(three_d_page)
    stack.setCurrentIndex(0)
    layout.addWidget(stack, 1)

    mode_row = QHBoxLayout()
    mode_row.setContentsMargins(0, 0, 0, 0)
    mode_row.setSpacing(6)
    mode_group = QButtonGroup(dialog)
    mode_group.setExclusive(True)

    image_mode = QPushButton(_txt("이미지", "Image"))
    image_mode.setObjectName("secondary")
    image_mode.setCheckable(True)
    image_mode.setChecked(True)
    image_mode.setMinimumWidth(78)
    mode_group.addButton(image_mode, 0)
    mode_row.addWidget(image_mode)

    three_d_mode = QPushButton("3D")
    three_d_mode.setObjectName("secondary")
    three_d_mode.setCheckable(True)
    three_d_mode.setMinimumWidth(78)
    mode_group.addButton(three_d_mode, 1)
    mode_row.addWidget(three_d_mode)
    mode_row.addStretch(1)
    layout.addLayout(mode_row)

    controls = QWidget()
    controls_layout = QHBoxLayout(controls)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(6)
    controls_layout.addStretch(1)

    minus_button = QToolButton()
    minus_button.setText("−")
    minus_button.setToolTip(tr("image.zoom_out"))
    minus_button.setAccessibleName(tr("image.zoom_out_accessible"))
    minus_button.setFixedSize(38, 34)
    minus_button.clicked.connect(lambda: viewer.zoom_by(0.8))

    actual_button = QPushButton("100%")
    actual_button.setObjectName("secondary")
    actual_button.setToolTip(tr("image.actual_size"))
    actual_button.clicked.connect(viewer.actual_size)

    fit_button = QPushButton(tr("image.fit"))
    fit_button.setObjectName("secondary")
    fit_button.setToolTip(tr("image.fit_tip"))
    fit_button.clicked.connect(viewer.fit_image)

    plus_button = QToolButton()
    plus_button.setText("+")
    plus_button.setToolTip(tr("image.zoom_in"))
    plus_button.setAccessibleName(tr("image.zoom_in_accessible"))
    plus_button.setFixedSize(38, 34)
    plus_button.clicked.connect(lambda: viewer.zoom_by(1.25))

    for button in (minus_button, plus_button):
        button.setStyleSheet(
            "QToolButton { background:white; color:#303341; "
            "border:1px solid #dfe1e8; border-radius:8px; "
            "font-size:16pt; font-weight:600; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:#f5f2ff; }"
        )

    controls_layout.addWidget(minus_button)
    controls_layout.addWidget(actual_button)
    controls_layout.addWidget(fit_button)
    controls_layout.addWidget(plus_button)
    controls_layout.addStretch(1)
    layout.addWidget(controls)

    hint = QLabel(tr("image.hint"))
    hint.setObjectName("muted")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(hint)

    def switch_mode(index: int) -> None:
        stack.setCurrentIndex(index)
        image_controls = index == 0
        controls.setVisible(image_controls)
        hint.setText(
            tr("image.hint")
            if image_controls
            else _txt(
                "3D 백엔드 연결 전 UI 검증 단계입니다.",
                "3D UI validation stage; backend not connected yet.",
            )
        )

    mode_group.idClicked.connect(switch_mode)

    # Stable object references make the shell straightforward to regression-test
    # without coupling future backend implementation to this function's locals.
    dialog._fh6_preview_stack = stack
    dialog._fh6_preview_mode_buttons = (image_mode, three_d_mode)
    dialog._fh6_preview_3d_page = three_d_page
    dialog._fh6_preview_3d_message = three_d_message

    window._apply_pointing_cursors(dialog)
    dialog.exec()


def apply_v1_4_preview_mode_shell_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_preview_mode_shell_patched", False):
        return

    original_show = MainWindow._show_livery_image

    def show_preview(window: Any, record: object) -> None:
        # Tuning preview and every non-livery caller keep the exact #337 path.
        if not isinstance(record, LiveryRecord):
            original_show(window, record)
            return
        _show_livery_preview_shell(window, record)

    MainWindow._show_livery_image = show_preview
    MainWindow._fh6_v14_preview_mode_shell_patched = True
