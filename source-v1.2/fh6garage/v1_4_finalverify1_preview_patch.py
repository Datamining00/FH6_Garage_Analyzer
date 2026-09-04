from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .models import LiveryRecord
from .ui import APP_STYLE, ZoomableImageView


def _build_thumbnail_page(record: LiveryRecord, image: QImage) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    viewer = ZoomableImageView(QPixmap.fromImage(image))
    layout.addWidget(viewer, 1)

    controls = QHBoxLayout()
    controls.setContentsMargins(0, 0, 0, 0)
    controls.setSpacing(6)
    controls.addStretch(1)

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
            "QToolButton:hover { border-color:#8c74ee; "
            "background:#f5f2ff; }"
        )

    controls.addWidget(minus_button)
    controls.addWidget(actual_button)
    controls.addWidget(fit_button)
    controls.addWidget(plus_button)
    controls.addStretch(1)

    hint = QLabel(tr("image.hint"))
    hint.setObjectName("muted")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

    layout.addLayout(controls)
    layout.addWidget(hint)
    return page


def _build_3d_page() -> tuple[QWidget, dict[str, Any]]:
    page = QWidget()
    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(8)

    status = QLabel("3D 탭을 선택하면 이 리버리를 4x / UV3 / Legacy로 렌더링합니다.")
    status.setObjectName("muted")
    status.setWordWrap(True)
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(status)

    host = QWidget()
    host_layout = QVBoxLayout(host)
    host_layout.setContentsMargins(0, 0, 0, 0)
    host_layout.setSpacing(0)
    placeholder = QLabel("3D 모델 준비 전")
    placeholder.setObjectName("muted")
    placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
    host_layout.addWidget(placeholder, 1)
    root.addWidget(host, 1)

    controls = QHBoxLayout()
    controls.setContentsMargins(0, 0, 0, 0)
    controls.setSpacing(6)

    resolution = QComboBox()
    for key, label in (
        ("normal", "1x"),
        ("high", "2x"),
        ("ultra4x", "4x"),
        ("extreme8x", "8x"),
        ("experimental16x", "16x"),
    ):
        resolution.addItem(label, key)
    resolution.setCurrentIndex(resolution.findData("ultra4x"))
    resolution.setToolTip("리버리 렌더링 배율")

    eligibility = QComboBox()
    eligibility.addItem("Legacy", "legacy")
    eligibility.addItem("Strict", "strict")
    eligibility.addItem("Declared + confirmed", "declared_confirmed")
    eligibility.setCurrentIndex(eligibility.findData("legacy"))
    eligibility.setToolTip("리버리 적용 대상 정책")

    uv = QComboBox()
    for channel in (0, 1, 2, 3):
        uv.addItem(f"UV{channel}", channel)
    uv.setCurrentIndex(uv.findData(3))
    uv.setToolTip("리버리 렌더링에 사용할 TEXCOORD 채널")

    cleanup_ab = QCheckBox("A+B 정리")
    cleanup_ab.setChecked(True)
    cleanup_ab.setToolTip("rim/presentation/support/thin cleanup")

    cleanup_c = QCheckBox("C 추가 정리")
    cleanup_c.setChecked(False)
    cleanup_c.setToolTip("additional alternate-presentation cleanup")

    apply_button = QPushButton("3D 렌더링 / 적용")
    apply_button.setObjectName("secondary")
    reset_button = QPushButton("카메라 초기화")
    reset_button.setObjectName("secondary")
    reset_button.setEnabled(False)

    controls.addWidget(QLabel("배율"))
    controls.addWidget(resolution)
    controls.addWidget(QLabel("정책"))
    controls.addWidget(eligibility)
    controls.addWidget(QLabel("UV"))
    controls.addWidget(uv)
    controls.addWidget(cleanup_ab)
    controls.addWidget(cleanup_c)
    controls.addStretch(1)
    controls.addWidget(reset_button)
    controls.addWidget(apply_button)
    root.addLayout(controls)

    return page, {
        "status": status,
        "viewer_layout": host_layout,
        "placeholder": placeholder,
        "resolution": resolution,
        "eligibility": eligibility,
        "uv": uv,
        "cleanup_ab": cleanup_ab,
        "cleanup_c": cleanup_c,
        "apply": apply_button,
        "reset": reset_button,
    }


def _show_livery_preview(window: Any, record: LiveryRecord) -> None:
    path = record.thumbnail_path
    if not path or not path.is_file():
        QMessageBox.information(
            window,
            tr("image.none_title"),
            tr("image.none_message"),
        )
        return

    try:
        image = QImage.fromData(path.read_bytes())
    except OSError as exc:
        QMessageBox.warning(window, tr("image.read_failed"), str(exc))
        return
    if image.isNull():
        QMessageBox.warning(
            window,
            tr("image.read_failed"),
            tr("image.format_failed"),
        )
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

    tabs = QTabWidget()
    thumbnail_page = _build_thumbnail_page(record, image)
    three_d_page, controls = _build_3d_page()
    tabs.addTab(thumbnail_page, "썸네일")
    tabs.addTab(three_d_page, "3D")
    layout.addWidget(tabs, 1)

    controller_holder: dict[str, Any] = {"controller": None}

    def ensure_3d(index: int) -> None:
        if index != 1 or controller_holder["controller"] is not None:
            return
        try:
            from .preview3d.integration import Preview3DController

            controller = Preview3DController(
                window=window,
                dialog=dialog,
                record=record,
                viewer_layout=controls["viewer_layout"],
                status_label=controls["status"],
                controls=controls,
            )
        except Exception as exc:
            controls["status"].setText(
                f"3D 백엔드를 불러올 수 없습니다.\n{type(exc).__name__}: {exc}"
            )
            return
        controller_holder["controller"] = controller
        dialog._fh6_finalverify1_3d_controller = controller
        placeholder = controls.get("placeholder")
        if placeholder is not None:
            controls["viewer_layout"].removeWidget(placeholder)
            placeholder.hide()
            placeholder.deleteLater()
            controls["placeholder"] = None
        controller.start()

    tabs.currentChanged.connect(ensure_3d)

    window._apply_pointing_cursors(dialog)
    dialog.exec()


def apply_v1_4_finalverify1_preview_patch(MainWindow: Any) -> None:
    """Add FinalVerify1 3D livery rendering to the existing livery-card magnifier."""
    if getattr(MainWindow, "_fh6_v14_finalverify1_preview_patched", False):
        return

    original_show_livery_image = MainWindow._show_livery_image

    def show_livery_image(window: Any, record: Any) -> None:
        if not isinstance(record, LiveryRecord):
            original_show_livery_image(window, record)
            return
        _show_livery_preview(window, record)

    MainWindow._show_livery_image = show_livery_image
    MainWindow._fh6_v14_finalverify1_preview_patched = True
