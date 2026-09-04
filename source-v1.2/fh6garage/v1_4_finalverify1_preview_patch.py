from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
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
    page.setObjectName("finalverify3dPage")
    root = QVBoxLayout(page)
    root.setContentsMargins(8, 8, 8, 8)
    root.setSpacing(8)

    progress_panel = QFrame()
    progress_panel.setObjectName("progressPanel")
    progress_layout = QVBoxLayout(progress_panel)
    progress_layout.setContentsMargins(14, 9, 14, 9)
    progress_layout.setSpacing(5)

    progress_title = QLabel("3D 모델 준비 중")
    progress_title.setObjectName("progressTitle")
    progress_layout.addWidget(progress_title)

    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setFormat("0%")
    progress.setTextVisible(True)
    progress.setFixedHeight(16)
    progress_layout.addWidget(progress)

    status = QLabel("3D 탭을 선택하면 이 리버리를 4x / UV3 / Legacy로 렌더링합니다.")
    status.setObjectName("progressDetail")
    status.setWordWrap(True)
    progress_layout.addWidget(status)
    root.addWidget(progress_panel)

    host = QWidget()
    host.setObjectName("renderHost")
    host_layout = QVBoxLayout(host)
    host_layout.setContentsMargins(0, 0, 0, 0)
    host_layout.setSpacing(0)

    placeholder = QFrame()
    placeholder.setObjectName("loadingPlaceholder")
    placeholder_layout = QVBoxLayout(placeholder)
    placeholder_layout.setContentsMargins(24, 24, 24, 24)
    placeholder_layout.addStretch(1)
    placeholder_title = QLabel("3D 모델과 리버리를 준비하고 있습니다")
    placeholder_title.setObjectName("loadingTitle")
    placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    placeholder_subtitle = QLabel("상단 진행률에서 전체 작업 상태를 확인할 수 있습니다.")
    placeholder_subtitle.setObjectName("loadingSubtitle")
    placeholder_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    placeholder_layout.addWidget(placeholder_title)
    placeholder_layout.addWidget(placeholder_subtitle)
    placeholder_layout.addStretch(1)
    host_layout.addWidget(placeholder, 1)
    root.addWidget(host, 1)

    toolbar = QFrame()
    toolbar.setObjectName("controlBar")
    controls = QHBoxLayout(toolbar)
    controls.setContentsMargins(12, 8, 12, 8)
    controls.setSpacing(8)

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
    resolution.setMinimumWidth(76)

    eligibility = QComboBox()
    eligibility.addItem("Legacy", "legacy")
    eligibility.addItem("Strict", "strict")
    eligibility.addItem("Declared + confirmed", "declared_confirmed")
    eligibility.setCurrentIndex(eligibility.findData("legacy"))
    eligibility.setToolTip("리버리 적용 대상 정책")
    eligibility.setMinimumWidth(170)

    uv = QComboBox()
    for channel in (0, 1, 2, 3):
        uv.addItem(f"UV{channel}", channel)
    uv.setCurrentIndex(uv.findData(3))
    uv.setToolTip("리버리 렌더링에 사용할 TEXCOORD 채널")
    uv.setMinimumWidth(78)

    cleanup_ab = QCheckBox("A+B 정리")
    cleanup_ab.setChecked(True)
    cleanup_ab.setToolTip("rim/presentation/support/thin cleanup")

    cleanup_c = QCheckBox("C 추가 정리")
    cleanup_c.setChecked(False)
    cleanup_c.setToolTip("additional alternate-presentation cleanup")

    apply_button = QPushButton("3D 렌더링 / 적용")
    apply_button.setObjectName("primary3d")
    reset_button = QPushButton("카메라 초기화")
    reset_button.setObjectName("secondary3d")
    reset_button.setEnabled(False)

    label_scale = QLabel("배율")
    label_policy = QLabel("정책")
    label_uv = QLabel("UV")
    for label in (label_scale, label_policy, label_uv):
        label.setObjectName("controlLabel")

    controls.addWidget(label_scale)
    controls.addWidget(resolution)
    controls.addSpacing(4)
    controls.addWidget(label_policy)
    controls.addWidget(eligibility)
    controls.addSpacing(4)
    controls.addWidget(label_uv)
    controls.addWidget(uv)
    controls.addSpacing(8)
    controls.addWidget(cleanup_ab)
    controls.addWidget(cleanup_c)
    controls.addStretch(1)
    controls.addWidget(reset_button)
    controls.addWidget(apply_button)
    root.addWidget(toolbar)

    page.setStyleSheet(
        """
        QWidget#finalverify3dPage { background: #20242a; }
        QFrame#progressPanel {
            background: #292e35; border: 1px solid #3a4049; border-radius: 8px;
        }
        QLabel#progressTitle { color: #f2f4f7; font-weight: 600; font-size: 10.5pt; }
        QLabel#progressDetail { color: #aeb5c0; font-size: 9pt; }
        QProgressBar {
            background: #3a4049; color: #f7f7fa; border: 0; border-radius: 7px;
            text-align: center; font-size: 8.5pt; font-weight: 600;
        }
        QProgressBar::chunk { background: #8c74ee; border-radius: 7px; }
        QWidget#renderHost { background: #4a5058; border: 1px solid #343941; border-radius: 6px; }
        QFrame#loadingPlaceholder { background: #4a5058; border-radius: 6px; }
        QLabel#loadingTitle { color: #f0f2f5; font-size: 12pt; font-weight: 600; }
        QLabel#loadingSubtitle { color: #c0c5cc; font-size: 9pt; }
        QFrame#controlBar {
            background: #292e35; border: 1px solid #3a4049; border-radius: 8px;
        }
        QLabel#controlLabel, QFrame#controlBar QCheckBox { color: #dfe3e8; }
        QFrame#controlBar QComboBox {
            min-height: 30px; background: #363c45; color: #f3f4f6;
            border: 1px solid #4a515c; border-radius: 6px; padding: 0 8px;
        }
        QFrame#controlBar QComboBox:disabled, QFrame#controlBar QCheckBox:disabled {
            color: #8e96a2; background: #30353c;
        }
        QFrame#controlBar QPushButton {
            min-height: 30px; padding: 0 13px; border-radius: 6px; font-weight: 600;
        }
        QPushButton#secondary3d {
            background: #363c45; color: #e7eaee; border: 1px solid #4a515c;
        }
        QPushButton#secondary3d:hover { background: #404751; }
        QPushButton#primary3d {
            background: #8067e8; color: white; border: 1px solid #947ff0;
        }
        QPushButton#primary3d:hover { background: #8c74ee; }
        QPushButton#primary3d:disabled, QPushButton#secondary3d:disabled {
            background: #30353c; color: #7f8792; border-color: #3b4149;
        }
        """
    )

    return page, {
        "status": status,
        "progress": progress,
        "progress_title": progress_title,
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
