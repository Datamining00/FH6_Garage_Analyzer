from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


DEFAULT_THUMBNAIL_ASPECT = 16.0 / 9.0
_QT_MAX_WIDGET_SIZE = 16777215


class _AspectFitThumbnailController(QObject):
    """Keep one saved-content thumbnail fully visible at its native aspect.

    v1.3.x rendered card thumbnails through a fixed wide target size. A normal
    16:9 FH thumbnail could therefore be cropped vertically, and the card used
    a fixed vertical size policy which made the clipping more visible at some
    window widths / DPI scales. This controller makes the image host follow the
    decoded thumbnail aspect ratio and always uses KeepAspectRatio rendering.
    """

    _WATCHED_EVENTS = {
        QEvent.Type.Resize,
        QEvent.Type.Show,
        QEvent.Type.LayoutRequest,
        QEvent.Type.PolishRequest,
    }

    def __init__(self, card: QWidget, label: QLabel) -> None:
        super().__init__(card)
        self.card = card
        self.label = label
        self.host = label.parentWidget()
        self._source = QPixmap()
        self._aspect = DEFAULT_THUMBNAIL_ASPECT
        self._pending = False
        self._applying = False

        label.setScaledContents(False)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumHeight(0)
        label.setMaximumHeight(_QT_MAX_WIDGET_SIZE)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # The card must be allowed to grow with the aspect-correct image host.
        card.setMinimumHeight(0)
        card.setMaximumHeight(_QT_MAX_WIDGET_SIZE)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if self.host is not None:
            self.host.setMinimumHeight(1)
            self.host.setMaximumHeight(_QT_MAX_WIDGET_SIZE)
            self.host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.host.installEventFilter(self)
        label.installEventFilter(self)
        card.installEventFilter(self)

        self.schedule()

    @property
    def aspect_ratio(self) -> float:
        return self._aspect

    def set_source(self, pixmap: QPixmap) -> None:
        self._source = QPixmap(pixmap)
        if not self._source.isNull() and self._source.height() > 0:
            self._aspect = max(
                0.05,
                float(self._source.width()) / float(self._source.height()),
            )
        else:
            self._aspect = DEFAULT_THUMBNAIL_ASPECT
        self.schedule()

    def clear_source(self) -> None:
        self._source = QPixmap()
        self._aspect = DEFAULT_THUMBNAIL_ASPECT
        self.label.setPixmap(QPixmap())
        self.schedule()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._WATCHED_EVENTS:
            self.schedule()
        return False

    def schedule(self) -> None:
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self.apply)

    def _host_width(self) -> int:
        if self.host is not None and self.host.width() > 1:
            return self.host.width()
        # Card content margins are 12 px on each side in the current UI. The
        # fallback only runs before the first native layout pass.
        return max(1, self.card.width() - 24)

    def target_height(self, width: int | None = None) -> int:
        use_width = max(1, int(width if width is not None else self._host_width()))
        return max(1, int(round(use_width / max(self._aspect, 0.05))))

    def apply(self) -> None:
        self._pending = False
        if self._applying:
            return
        self._applying = True
        try:
            width = self._host_width()
            height = self.target_height(width)

            if self.host is not None and self.host.height() != height:
                self.host.setFixedHeight(height)

            if not self._source.isNull():
                target = QSize(width, height)
                rendered = self._source.scaled(
                    target,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.label.setPixmap(rendered)
                self.label.setText("")

            self.card.updateGeometry()
            parent = self.card.parentWidget()
            layout = parent.layout() if parent is not None else None
            if layout is not None:
                layout.invalidate()
        finally:
            self._applying = False


def _relax_fixed_card_text_heights(card: QWidget, image_label: QLabel) -> None:
    """Avoid DPI/font clipping in card metadata without changing its styling."""
    for label in card.findChildren(QLabel):
        if label is image_label:
            continue
        # Metadata labels in v1.3.x were fixed to 28/31 px. Preserve that as a
        # minimum but allow Qt to request more height at fractional DPI scales.
        if label.minimumHeight() == label.maximumHeight() and label.maximumHeight() <= 64:
            minimum = max(label.minimumHeight(), label.sizeHint().height())
            label.setMinimumHeight(minimum)
            label.setMaximumHeight(_QT_MAX_WIDGET_SIZE)
            policy = label.sizePolicy()
            label.setSizePolicy(policy.horizontalPolicy(), QSizePolicy.Policy.Preferred)


def _configure_aspect_card(card: QWidget) -> None:
    label = getattr(card, "_fh6_image_label", None)
    if not isinstance(label, QLabel):
        return
    if getattr(card, "_fh6_aspect_thumbnail_controller", None) is not None:
        return

    _relax_fixed_card_text_heights(card, label)
    controller = _AspectFitThumbnailController(card, label)
    card._fh6_aspect_thumbnail_controller = controller


def _load_original_pixmap(path: Any) -> QPixmap:
    if path is None:
        return QPixmap()
    try:
        candidate = Path(path)
    except TypeError:
        return QPixmap()
    if not candidate.is_file():
        return QPixmap()
    pixmap = QPixmap(str(candidate))
    return pixmap if not pixmap.isNull() else QPixmap()


def apply_v1_3_2_global_ui_patch(MainWindow) -> None:
    """Globally prevent saved-content card/thumbnail clipping.

    This patch is intentionally limited to geometry/aspect handling. Icon size,
    icon color and action placement are handled in the next UI step.
    """
    if getattr(MainWindow, "_fh6_v132_global_ui_patched", False):
        return

    original_make_card = MainWindow._make_saved_content_card
    original_load_thumbnail = MainWindow._load_livery_card_thumbnail
    original_unload_thumbnail = MainWindow._unload_livery_card_thumbnail

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        _configure_aspect_card(card)
        return card

    def patched_load_thumbnail(self, card) -> None:
        if getattr(card, "_fh6_thumbnail_loaded", False):
            controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
            if controller is not None:
                controller.schedule()
            return

        label = getattr(card, "_fh6_image_label", None)
        controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
        if not isinstance(label, QLabel) or controller is None:
            original_load_thumbnail(self, card)
            return

        path = getattr(card, "_fh6_thumbnail_path", None)
        pixmap = _load_original_pixmap(path)
        if pixmap.isNull():
            # Preserve support for any thumbnail format/path handled by the
            # older loader. If it succeeds, aspect-fit its rendered result.
            original_load_thumbnail(self, card)
            fallback = label.pixmap()
            if fallback is not None and not fallback.isNull():
                controller.set_source(fallback)
            else:
                controller.clear_source()
            return

        label.setObjectName("muted")
        controller.set_source(pixmap)
        card._fh6_thumbnail_loaded = True

    def patched_unload_thumbnail(self, card) -> None:
        controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
        if controller is None:
            original_unload_thumbnail(self, card)
            return
        if not getattr(card, "_fh6_thumbnail_loaded", False):
            return

        controller.clear_source()
        label = getattr(card, "_fh6_image_label", None)
        if isinstance(label, QLabel):
            label.setText("Thumbnail")
            label.setObjectName("muted")
        card._fh6_thumbnail_loaded = False

    MainWindow._make_saved_content_card = patched_make_card
    MainWindow._load_livery_card_thumbnail = patched_load_thumbnail
    MainWindow._unload_livery_card_thumbnail = patched_unload_thumbnail
    MainWindow._fh6_v132_global_ui_patched = True
