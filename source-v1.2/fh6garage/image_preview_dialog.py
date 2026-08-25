from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .models import LiveryRecord, TuningRecord


class ZoomableImageView(QGraphicsView):
    """Image viewer with wheel zoom, hand-pan, 100%, and fit-to-window."""

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#f1f2f6"))
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._min_scale = 0.05
        self._max_scale = 16.0
        QTimer.singleShot(0, self.fit_image)

    def current_scale(self) -> float:
        return float(self.transform().m11())

    def zoom_by(self, factor: float) -> None:
        current = self.current_scale()
        if current <= 0:
            return

        target = max(
            self._min_scale,
            min(self._max_scale, current * float(factor)),
        )
        self.scale(target / current, target / current)

    def fit_image(self) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        self.resetTransform()
        self.fitInView(
            self._pixmap_item,
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def actual_size(self) -> None:
        self.resetTransform()
        self.centerOn(self._pixmap_item)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        steps = delta / 120.0
        self.zoom_by(1.25 ** steps)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.actual_size()
        event.accept()


def show_livery_image(
    owner: Any,
    record: LiveryRecord | TuningRecord,
    *,
    app_style: str,
) -> None:
    path = record.thumbnail_path
    if not path or not path.is_file():
        QMessageBox.information(
            owner,
            tr("image.none_title"),
            tr("image.none_message"),
        )
        return

    try:
        image = QImage.fromData(path.read_bytes())
    except OSError as exc:
        QMessageBox.warning(owner, tr("image.read_failed"), str(exc))
        return

    if image.isNull():
        QMessageBox.warning(
            owner,
            tr("image.read_failed"),
            tr("image.format_failed"),
        )
        return

    dialog = QDialog(owner)
    livery_name = record.header.name or "(unnamed)"
    car_name = owner._car_label(record.header.car_id)
    dialog.setWindowTitle(f"{livery_name} — {car_name}")
    dialog.setModal(True)
    dialog.setStyleSheet(app_style + "QDialog { background:#f7f8fb; }")

    available = owner.screen().availableGeometry()
    target_w = max(900, min(1500, int(available.width() * 0.92)))
    target_h = max(620, min(960, int(available.height() * 0.90)))
    dialog.resize(target_w, target_h)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 12, 12, 12)
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

    owner._apply_pointing_cursors(dialog)
    dialog.exec()
