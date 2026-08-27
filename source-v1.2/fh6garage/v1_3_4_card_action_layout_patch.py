from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import QGridLayout, QLayout, QToolButton, QVBoxLayout, QWidget

from . import v1_3_2_change_dialog_runtime_fix as _legacy_runtime
from .i18n import tr
from .ui import CopyValueLabel


ICON_SIZE = 20
EDGE_MARGIN = 5
BUTTON_GAP = 5
ROW_HEIGHT = 38
THUMBNAIL_MIN_HEIGHT = 270
CARD_MIN_HEIGHT = 350
CARD_METADATA_HEIGHT = 80


def _line_icon(kind: str, *, active: bool = False) -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#6e4bf2" if active else "#555a68")
    painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "memo":
        painter.drawRoundedRect(QRect(3, 2, 12, 15), 2, 2)
        painter.drawLine(6, 6, 12, 6)
        painter.drawLine(6, 9, 11, 9)
        painter.drawLine(11, 15, 17, 9)
        painter.drawLine(13, 17, 17, 13)
    elif kind == "info":
        painter.drawEllipse(QRect(2, 2, 16, 16))
        painter.drawPoint(10, 6)
        painter.drawLine(10, 9, 10, 14)
    elif kind == "folder":
        path = QPolygon([QPoint(2, 6), QPoint(7, 6), QPoint(9, 8), QPoint(18, 8), QPoint(17, 17), QPoint(2, 17)])
        painter.drawPolyline(path)
        painter.drawLine(2, 6, 2, 17)
    elif kind == "export":
        painter.drawRoundedRect(QRect(2, 3, 11, 14), 1.5, 1.5)
        painter.drawLine(8, 10, 18, 10)
        painter.drawLine(14, 6, 18, 10)
        painter.drawLine(14, 14, 18, 10)
    elif kind == "lock":
        painter.drawRoundedRect(QRect(3, 8, 14, 10), 2, 2)
        if active:
            painter.drawArc(QRect(6, 2, 8, 11), 0, 180 * 16)
        else:
            painter.drawArc(QRect(8, 2, 8, 11), 20 * 16, 150 * 16)
    painter.end()
    return QIcon(pixmap)


def _remove_from_layout(layout: QLayout | None, widget: QWidget) -> None:
    if layout is None:
        return
    layout.removeWidget(widget)
    for index in range(layout.count()):
        child = layout.itemAt(index).layout()
        if child is not None:
            _remove_from_layout(child, widget)


def _clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child = item.layout()
        if child is not None:
            _clear_layout(child)
            child.deleteLater()


def _card_overlay(card: Any) -> QWidget | None:
    image = getattr(card, "_fh6_image_label", None)
    host = image.parentWidget() if image is not None else None
    stack = host.layout() if host is not None else None
    overlay = stack.currentWidget() if stack is not None and hasattr(stack, "currentWidget") else None
    return overlay if isinstance(overlay, QWidget) else None


class _SixRowActionAligner(QObject):
    _EVENTS = {
        QEvent.Type.Show,
        QEvent.Type.Resize,
        QEvent.Type.LayoutRequest,
        QEvent.Type.PolishRequest,
    }

    def __init__(self, overlay: QWidget, left: list[QToolButton], right: list[QToolButton]) -> None:
        super().__init__(overlay)
        self.overlay = overlay
        self.left = left
        self.right = right
        overlay.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._EVENTS:
            QTimer.singleShot(0, self.reposition)
        return False

    def reposition(self) -> None:
        if self.overlay.width() <= 0:
            return
        for column, buttons in (("left", self.left), ("right", self.right)):
            for row, button in enumerate(buttons):
                x = EDGE_MARGIN if column == "left" else self.overlay.width() - EDGE_MARGIN - button.width()
                y = EDGE_MARGIN + row * (ROW_HEIGHT + BUTTON_GAP) + (ROW_HEIGHT - button.height()) // 2
                button.move(max(0, x), max(0, y))
                button.raise_()


class _ActionLayerResizer(QObject):
    """Keep the dedicated action layer exactly over the thumbnail overlay."""

    _EVENTS = {QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.LayoutRequest}

    def __init__(self, overlay: QWidget, layer: QWidget) -> None:
        super().__init__(overlay)
        self.overlay = overlay
        self.layer = layer
        overlay.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._EVENTS:
            self.resize_layer()
        return False

    def resize_layer(self) -> None:
        self.layer.setGeometry(self.overlay.rect())
        self.layer.raise_()


def _disable_old_aligners(card: Any, overlay: QWidget) -> None:
    for name in (
        "_fh6_card_action_aligner",
        "_fh6_four_left_action_aligner",
        "_fh6_applied_state_aligner",
        "_fh6_hide_aligner",
    ):
        aligner = getattr(card, name, None)
        if isinstance(aligner, QObject):
            overlay.removeEventFilter(aligner)
            # Older patches also queued direct QTimer callbacks. Removing the
            # event filter does not cancel those already queued calls, so make
            # their eventual reposition harmless as well.
            if hasattr(aligner, "overlay"):
                aligner.overlay = None
            if hasattr(aligner, "card"):
                aligner.card = None
            try:
                aligner.reposition = lambda: None
            except (AttributeError, RuntimeError, TypeError):
                pass


def _placeholder_button(overlay: QWidget, name: str, icon: QIcon, tooltip: str) -> QToolButton:
    button = QToolButton(overlay)
    button.setObjectName(name)
    button.setFixedSize(34, 34)
    button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    button.setIcon(icon)
    button.setToolTip(tooltip)
    button.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,238); border:1px solid #dfe1e8; "
        "border-radius:8px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:#f2edff; }"
        "QToolButton:checked { border-color:#8c74ee; background:#eee9ff; }"
    )
    return button


def _unique_placeholder(card: Any, overlay: QWidget, attribute: str, name: str, kind: str, tooltip: str) -> QToolButton:
    existing = getattr(card, attribute, None)
    if isinstance(existing, QToolButton):
        return existing
    matches = overlay.findChildren(QToolButton, name)
    button = matches[0] if matches else _placeholder_button(overlay, name, _line_icon(kind), tooltip)
    for duplicate in matches[1:]:
        duplicate.hide()
        duplicate.deleteLater()
    setattr(card, attribute, button)
    return button


def _arrange_card(card: Any) -> None:
    if bool(card.property("fh6ArchiveCard")):
        return
    overlay = _card_overlay(card)
    image = getattr(card, "_fh6_image_label", None)
    if overlay is None or image is None:
        return

    required = {
        "move": getattr(card, "_fh6_game_move_button", None),
        "zoom": getattr(card, "_fh6_zoom_button", None),
        "memo": getattr(card, "_fh6_memo_button", None),
        "info": getattr(card, "_fh6_info_button", None),
        "folder": getattr(card, "_fh6_folder_button", None),
        "paint": getattr(card, "_fh6_applied_state_button", None),
        "hide": getattr(card, "_fh6_hide_button", None),
        "check": getattr(card, "_fh6_check_box", None),
        "triangle": getattr(card, "_fh6_triangle_box", None),
        "excluded": getattr(card, "_fh6_excluded_box", None),
    }
    if not all(isinstance(button, QToolButton) for button in required.values()):
        return

    root_layout = overlay.layout()
    if root_layout is None:
        return

    _disable_old_aligners(card, overlay)

    required["info"].setIcon(_line_icon("info"))
    required["folder"].setIcon(_line_icon("folder"))

    lock = _unique_placeholder(
        card, overlay, "_fh6_lock_placeholder_button", "fh6LockPlaceholderButton", "lock", "잠금 기능 준비 중"
    )
    if not lock.isCheckable():
        lock.setCheckable(True)
        lock.toggled.connect(lambda active, target=lock: target.setIcon(_line_icon("lock", active=active)))
    export = _unique_placeholder(
        card, overlay, "_fh6_export_placeholder_button", "fh6ExportPlaceholderButton", "export", "내보내기 기능 준비 중"
    )
    export.setEnabled(False)

    left = [required[name] for name in ("move", "zoom", "memo", "info", "folder")]
    left.append(export)
    right = [required[name] for name in ("paint",)]
    right.append(lock)
    right.extend(required[name] for name in ("hide", "check", "triangle", "excluded"))

    # Do not reuse the historical overlay layout. Several maintenance patches
    # still own nested layouts there. A dedicated child layer gives this patch
    # sole and stable ownership of all twelve action buttons.
    old_layer = getattr(card, "_fh6_v134_action_layer", None)
    if isinstance(old_layer, QWidget):
        old_layer.hide()
        old_layer.deleteLater()
    layer = QWidget(overlay)
    layer.setObjectName("fh6CardActionLayer")
    layer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    layer.setStyleSheet("background: transparent;")
    layer.setGeometry(overlay.rect())
    grid = QGridLayout(layer)
    grid.setContentsMargins(EDGE_MARGIN, EDGE_MARGIN, EDGE_MARGIN, EDGE_MARGIN)
    grid.setHorizontalSpacing(0)
    grid.setVerticalSpacing(BUTTON_GAP)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    for row, (left_button, right_button) in enumerate(zip(left, right)):
        for button in (left_button, right_button):
            _remove_from_layout(root_layout, button)
            button.setParent(layer)
            button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            button.show()
        grid.setRowMinimumHeight(row, ROW_HEIGHT)
        grid.addWidget(left_button, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(right_button, row, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def enforce_grid() -> None:
        grid.invalidate()
        grid.activate()

    resizer = _ActionLayerResizer(overlay, layer)
    card._fh6_v134_action_layer = layer
    card._fh6_v134_action_layer_resizer = resizer
    card._fh6_v134_action_grid = grid
    layer.show()
    resizer.resize_layer()

    image.setMinimumHeight(THUMBNAIL_MIN_HEIGHT)
    card.setMinimumHeight(CARD_MIN_HEIGHT)
    aspect = getattr(card, "_fh6_aspect_thumbnail_controller", None)
    original_target_height = getattr(aspect, "target_height", None)
    if callable(original_target_height) and not bool(getattr(aspect, "_fh6_v134_minimum_installed", False)):
        aspect.target_height = lambda width=None, target=original_target_height: max(
            THUMBNAIL_MIN_HEIGHT,
            target(width),
        )
        aspect._fh6_v134_minimum_installed = True
        original_apply = aspect.apply

        def apply_with_card_height() -> None:
            original_apply()
            host = getattr(aspect, "host", None)
            host_height = host.height() if host is not None else THUMBNAIL_MIN_HEIGHT
            card.setMinimumHeight(max(CARD_MIN_HEIGHT, host_height + CARD_METADATA_HEIGHT))

        aspect.apply = apply_with_card_height
        aspect.schedule()
        QTimer.singleShot(0, apply_with_card_height)
        QTimer.singleShot(50, apply_with_card_height)
    QTimer.singleShot(0, enforce_grid)
    QTimer.singleShot(50, enforce_grid)
    QTimer.singleShot(150, enforce_grid)

    outer = card.layout()
    if isinstance(outer, QVBoxLayout):
        outer.setSpacing(3)
    for label in card.findChildren(CopyValueLabel):
        if label.prefix == tr("card.vehicle_label"):
            label.setStyleSheet(
                "QLabel { background:transparent; color:#171924; border:0; "
                "padding:1px 2px 0 2px; font-size:11.5pt; font-weight:700; }"
            )
            label.setFixedHeight(26)
        elif label.prefix == tr("card.title_label"):
            label.setStyleSheet(
                "QLabel { background:transparent; color:#343744; border:0; "
                "padding:0 2px; font-size:10pt; font-weight:600; }"
            )
            label.setFixedHeight(24)
        elif label.prefix == tr("card.creator_label"):
            label.setStyleSheet(
                "QLabel { background:transparent; color:#6d7282; border:0; "
                "padding:0 2px; font-size:9.5pt; font-weight:500; }"
            )
            label.setFixedHeight(24)


def apply_v1_3_4_card_action_layout_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_card_action_layout_patched", False):
        return
    original_make_card = MainWindow._make_saved_content_card

    def make_card(self: Any, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery":
            _arrange_card(card)
        return card

    @staticmethod
    def memo_icon(has_note: bool) -> QIcon:
        return _line_icon("memo", active=has_note)

    MainWindow._make_saved_content_card = make_card
    MainWindow._detail_memo_icon = memo_icon
    # Timers queued by the legacy four-row patch resolve this module global at
    # execution time. Disable that obsolete geometry owner entirely.
    _legacy_runtime._force_card_action_geometry = lambda _card: None
    MainWindow._fh6_v134_card_action_layout_patched = True
