from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
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

from .i18n import get_language
from .models import LiveryRecord, TuningRecord
from .ui import APP_STYLE, ZoomableImageView


def _txt(ko: str, en: str) -> str:
    return ko if get_language().casefold().startswith("ko") else en


def _read_image(path: Path | None) -> QImage:
    if path is None or not path.is_file():
        return QImage()
    try:
        return QImage.fromData(path.read_bytes())
    except OSError:
        return QImage()


def _thumbnail_path(record: LiveryRecord | TuningRecord) -> Path | None:
    """Prefer the small in-container thumbnail when present, then fall back safely.

    The scanner intentionally stores the display image path used by the existing
    card/zoom workflow.  Preview mode must not change scan semantics, so the
    small thumbnail is discovered locally at view time only.
    """
    container = Path(record.container_path)
    for name in ("Thumb.png", "thumb.png"):
        candidate = container / name
        if candidate.is_file():
            return candidate
    return record.thumbnail_path


def _secondary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("secondary")
    return button


def _zoom_controls(viewer: ZoomableImageView, *, full: bool) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    if full:
        minus = QToolButton()
        minus.setText("−")
        minus.setFixedSize(38, 34)
        minus.setToolTip(_txt("축소", "Zoom out"))
        minus.clicked.connect(lambda: viewer.zoom_by(0.8))
        minus.setStyleSheet(
            "QToolButton { background:white; color:#303341; border:1px solid #dfe1e8; "
            "border-radius:8px; font-size:16pt; font-weight:600; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:#f5f2ff; }"
        )
        row.addWidget(minus)

    actual = _secondary_button("100%")
    actual.setToolTip(_txt("원본 크기로 표시", "Show at actual size"))
    actual.clicked.connect(viewer.actual_size)
    row.addWidget(actual)

    fit = _secondary_button(_txt("맞춤", "Fit"))
    fit.setToolTip(_txt("창에 맞춰 표시", "Fit image to window"))
    fit.clicked.connect(viewer.fit_image)
    row.addWidget(fit)

    if full:
        plus = QToolButton()
        plus.setText("+")
        plus.setFixedSize(38, 34)
        plus.setToolTip(_txt("확대", "Zoom in"))
        plus.clicked.connect(lambda: viewer.zoom_by(1.25))
        plus.setStyleSheet(
            "QToolButton { background:white; color:#303341; border:1px solid #dfe1e8; "
            "border-radius:8px; font-size:16pt; font-weight:600; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:#f5f2ff; }"
        )
        row.addWidget(plus)

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
    eligibility.addItem("Strict", "strict")
    eligibility.addItem("Legacy", "legacy")
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


def _show_preview_modes(window: Any, record: LiveryRecord | TuningRecord) -> None:
    image_path = record.thumbnail_path
    image = _read_image(image_path)
    if image.isNull():
        QMessageBox.information(
            window,
            _txt("이미지 없음", "No image"),
            _txt("표시할 이미지를 찾을 수 없습니다.", "No preview image is available."),
        )
        return

    thumbnail_image = _read_image(_thumbnail_path(record))
    if thumbnail_image.isNull():
        thumbnail_image = image

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
    root.setSpacing(7)

    content_stack = QStackedWidget()

    thumbnail_view = ZoomableImageView(QPixmap.fromImage(thumbnail_image))
    image_view = ZoomableImageView(QPixmap.fromImage(image))

    three_d_page = QWidget()
    three_d_layout = QVBoxLayout(three_d_page)
    three_d_layout.setContentsMargins(0, 0, 0, 0)
    three_d_message = QLabel(
        _txt(
            "3D 모드는 처음 선택할 때만 준비됩니다.",
            "3D mode is prepared only when selected for the first time.",
        )
    )
    three_d_message.setObjectName("muted")
    three_d_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
    three_d_message.setWordWrap(True)
    three_d_layout.addStretch(1)
    three_d_layout.addWidget(three_d_message)
    three_d_layout.addStretch(1)

    content_stack.addWidget(thumbnail_view)
    content_stack.addWidget(image_view)
    content_stack.addWidget(three_d_page)
    content_stack.setCurrentIndex(1)
    root.addWidget(content_stack, 1)

    mode_row = QHBoxLayout()
    mode_row.setContentsMargins(0, 0, 0, 0)
    mode_row.setSpacing(6)
    mode_group = QButtonGroup(dialog)
    mode_group.setExclusive(True)
    mode_buttons: list[QPushButton] = []
    for index, label in enumerate((
        _txt("썸네일", "Thumbnail"),
        _txt("이미지", "Image"),
        "3D",
    )):
        button = _secondary_button(label)
        button.setCheckable(True)
        button.setMinimumWidth(78)
        mode_group.addButton(button, index)
        mode_buttons.append(button)
        mode_row.addWidget(button)
    mode_buttons[1].setChecked(True)
    if not isinstance(record, LiveryRecord):
        mode_buttons[2].setEnabled(False)
        mode_buttons[2].setToolTip(
            _txt("3D 리버리 보기는 리버리 항목에서만 사용됩니다.", "3D livery preview is available for livery items only.")
        )
    mode_row.addStretch(1)
    root.addLayout(mode_row)

    options_stack = QStackedWidget()
    options_stack.addWidget(_zoom_controls(thumbnail_view, full=False))
    options_stack.addWidget(_zoom_controls(image_view, full=True))
    three_d_options, three_d_controls = _three_d_options()
    options_stack.addWidget(three_d_options)
    options_stack.setCurrentIndex(1)
    root.addWidget(options_stack)

    hint = QLabel(
        _txt(
            "마우스 휠: 확대/축소 · 드래그: 이동 · 더블클릭: 100%",
            "Mouse wheel: zoom · Drag: pan · Double-click: 100%",
        )
    )
    hint.setObjectName("muted")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(hint)

    prepared = {"requested": False}

    def prepare_three_d() -> None:
        if prepared["requested"]:
            return
        prepared["requested"] = True
        callback = getattr(window, "_fh6_prepare_livery_3d_preview", None)
        if not callable(callback):
            three_d_message.setText(
                _txt(
                    "3D UI 준비 완료 · 3D 백엔드는 다음 이식 단계에서 연결됩니다.",
                    "3D UI is ready · the 3D backend will be connected in the next integration stage.",
                )
            )
            return

        three_d_message.setText(_txt("3D 모델 준비 중...", "Preparing 3D model..."))

        def invoke_backend() -> None:
            try:
                callback(
                    dialog=dialog,
                    record=record,
                    page=three_d_page,
                    layout=three_d_layout,
                    message=three_d_message,
                    controls=three_d_controls,
                )
            except Exception as exc:  # backend failures must not break image modes
                three_d_message.setText(
                    _txt("3D 모델을 표시할 수 없습니다.\n", "Unable to display the 3D model.\n")
                    + f"{type(exc).__name__}: {exc}"
                )

        QTimer.singleShot(0, invoke_backend)

    def switch_mode(index: int) -> None:
        content_stack.setCurrentIndex(index)
        options_stack.setCurrentIndex(index)
        if index == 0:
            hint.setText(
                _txt("마우스 휠: 확대/축소 · 드래그: 이동", "Mouse wheel: zoom · Drag: pan")
            )
        elif index == 1:
            hint.setText(
                _txt(
                    "마우스 휠: 확대/축소 · 드래그: 이동 · 더블클릭: 100%",
                    "Mouse wheel: zoom · Drag: pan · Double-click: 100%",
                )
            )
        else:
            hint.setText(
                _txt(
                    "좌클릭: 회전 · 우클릭: 이동 · 마우스 휠: 확대/축소",
                    "Left-drag: rotate · Right-drag: pan · Mouse wheel: zoom",
                )
            )
            prepare_three_d()

    mode_group.idClicked.connect(switch_mode)

    # Expose stable handles for the upcoming 3D backend patch and regression tests.
    dialog._fh6_preview_content_stack = content_stack
    dialog._fh6_preview_options_stack = options_stack
    dialog._fh6_preview_mode_buttons = tuple(mode_buttons)
    dialog._fh6_preview_3d_controls = three_d_controls

    window._apply_pointing_cursors(dialog)
    dialog.exec()


def apply_v1_4_preview_mode_patch(MainWindow: Any) -> None:
    """Replace the zoom dialog with a three-mode preview shell.

    Image remains the default mode so the existing magnifier workflow is
    unchanged until the user explicitly chooses Thumbnail or 3D.
    """
    if getattr(MainWindow, "_fh6_v14_preview_modes_patched", False):
        return

    MainWindow._show_livery_image = _show_preview_modes
    MainWindow._fh6_v14_preview_modes_patched = True
