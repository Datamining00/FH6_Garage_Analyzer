from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
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


def _secondary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("secondary")
    return button


def _zoom_controls(viewer: ZoomableImageView) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    minus_button = QToolButton()
    minus_button.setText("−")
    minus_button.setToolTip(tr("image.zoom_out"))
    minus_button.setAccessibleName(tr("image.zoom_out_accessible"))
    minus_button.setFixedSize(38, 34)
    minus_button.clicked.connect(lambda: viewer.zoom_by(0.8))

    actual_button = _secondary_button("100%")
    actual_button.setToolTip(tr("image.actual_size"))
    actual_button.clicked.connect(viewer.actual_size)

    fit_button = _secondary_button(tr("image.fit"))
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

    row.addWidget(minus_button)
    row.addWidget(actual_button)
    row.addWidget(fit_button)
    row.addWidget(plus_button)
    row.addStretch(1)
    return holder


def _placeholder_options(text: str) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    label = QLabel(text)
    label.setObjectName("muted")
    row.addWidget(label)
    row.addStretch(1)
    return holder


def _three_d_options() -> tuple[QWidget, dict[str, Any]]:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)

    reset = _secondary_button(_txt("카메라 초기화", "Reset camera"))
    reset.setEnabled(False)

    eligibility = QComboBox()
    eligibility.addItem("Legacy", "legacy")
    eligibility.addItem("Strict", "strict")
    eligibility.setCurrentIndex(0)
    eligibility.setEnabled(False)

    cleanup_c = QCheckBox(_txt("C 추가 정리", "Additional cleanup C"))
    cleanup_c.setChecked(False)
    cleanup_c.setEnabled(False)

    row.addWidget(reset)
    row.addWidget(eligibility)
    row.addWidget(cleanup_c)
    row.addStretch(1)
    return holder, {
        "reset": reset,
        "eligibility": eligibility,
        "cleanup_c": cleanup_c,
    }


def _placeholder_page(text: str) -> tuple[QWidget, QLabel]:
    page = QWidget()
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(12, 12, 12, 12)
    message = QLabel(text)
    message.setObjectName("muted")
    message.setAlignment(Qt.AlignmentFlag.AlignCenter)
    message.setWordWrap(True)
    page_layout.addStretch(1)
    page_layout.addWidget(message)
    page_layout.addStretch(1)
    return page, message


def _show_livery_preview_shell(window: Any, record: LiveryRecord) -> None:
    """Stage-1 preview shell based directly on the validated #337 image path.

    The existing bigThumb.webp viewer is retained as Thumbnail mode. Image and
    3D are passive pages only: this stage intentionally imports no renderer,
    converter, OpenGL module, numpy, Pillow, or other new runtime dependency.
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

    root = QVBoxLayout(dialog)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(8)

    content_stack = QStackedWidget()

    # Mode 0: exact #337 source image (bigThumb.webp for liveries).
    thumbnail_view = ZoomableImageView(QPixmap.fromImage(image))
    content_stack.addWidget(thumbnail_view)

    # Modes 1 and 2 remain deliberately inert until their own validated stages.
    image_page, image_message = _placeholder_page(
        _txt(
            "이미지 렌더러는 다음 검증 단계에서 연결됩니다.",
            "The image renderer will be connected in a later validated stage.",
        )
    )
    three_d_page, three_d_message = _placeholder_page(
        _txt(
            "3D 백엔드는 다음 검증 단계에서 연결됩니다.",
            "The 3D backend will be connected in the next validated stage.",
        )
    )
    content_stack.addWidget(image_page)
    content_stack.addWidget(three_d_page)
    content_stack.setCurrentIndex(0)
    root.addWidget(content_stack, 1)

    mode_row = QHBoxLayout()
    mode_row.setContentsMargins(0, 0, 0, 0)
    mode_row.setSpacing(6)
    mode_group = QButtonGroup(dialog)
    mode_group.setExclusive(True)
    mode_buttons: list[QPushButton] = []
    for index, label in enumerate((_txt("썸네일", "Thumbnail"), _txt("이미지", "Image"), "3D")):
        button = _secondary_button(label)
        button.setCheckable(True)
        button.setMinimumWidth(78)
        mode_group.addButton(button, index)
        mode_buttons.append(button)
        mode_row.addWidget(button)
    mode_buttons[0].setChecked(True)
    mode_row.addStretch(1)
    root.addLayout(mode_row)

    options_stack = QStackedWidget()
    options_stack.addWidget(_zoom_controls(thumbnail_view))
    options_stack.addWidget(
        _placeholder_options(
            _txt("이미지 모드 옵션은 renderer 연결 후 활성화됩니다.", "Image options will be enabled with the renderer.")
        )
    )
    three_d_options, three_d_controls = _three_d_options()
    options_stack.addWidget(three_d_options)
    options_stack.setCurrentIndex(0)
    root.addWidget(options_stack)

    hint = QLabel(tr("image.hint"))
    hint.setObjectName("muted")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(hint)

    def switch_mode(index: int) -> None:
        content_stack.setCurrentIndex(index)
        options_stack.setCurrentIndex(index)
        if index == 0:
            hint.setText(tr("image.hint"))
        elif index == 1:
            hint.setText(
                _txt(
                    "이미지 backend 연결 전 UI 검증 단계입니다.",
                    "Image UI validation stage; backend not connected yet.",
                )
            )
        else:
            hint.setText(
                _txt(
                    "3D backend 연결 전 UI 검증 단계입니다.",
                    "3D UI validation stage; backend not connected yet.",
                )
            )

    mode_group.idClicked.connect(switch_mode)

    # Stable references are intentional. Later stages attach one backend at a
    # time without rebuilding or reinterpreting this already-validated shell.
    dialog._fh6_preview_content_stack = content_stack
    dialog._fh6_preview_options_stack = options_stack
    dialog._fh6_preview_mode_buttons = tuple(mode_buttons)
    dialog._fh6_preview_thumbnail_view = thumbnail_view
    dialog._fh6_preview_image_page = image_page
    dialog._fh6_preview_image_message = image_message
    dialog._fh6_preview_3d_page = three_d_page
    dialog._fh6_preview_3d_message = three_d_message
    dialog._fh6_preview_3d_controls = three_d_controls

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
