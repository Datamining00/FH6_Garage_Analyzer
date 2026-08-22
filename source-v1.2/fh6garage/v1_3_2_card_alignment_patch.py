from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLayout, QToolButton, QWidget


def _eye_slash_pixmap(active: bool, size: int = 22) -> QPixmap:
    """Draw one fixed eye-slash geometry for both checked and unchecked states."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = QColor("#6e4bf2" if active else "#8d93a2")
    pen = QPen(color, 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Symmetric eye outline. Active/inactive changes only the color, never shape.
    path = QPainterPath()
    path.moveTo(2.5, size / 2)
    path.cubicTo(6.0, 5.0, size - 6.0, 5.0, size - 2.5, size / 2)
    path.cubicTo(size - 6.0, size - 5.0, 6.0, size - 5.0, 2.5, size / 2)
    painter.drawPath(path)
    painter.drawEllipse(QRectF(size / 2 - 2.6, size / 2 - 2.6, 5.2, 5.2))
    painter.drawLine(3, 3, size - 3, size - 3)
    painter.end()
    return pixmap


def _remove_widget_from_layout(layout: QLayout | None, target: QWidget) -> bool:
    if layout is None:
        return False
    for index in reversed(range(layout.count())):
        item = layout.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if widget is target:
            layout.removeWidget(target)
            return True
        child_layout = item.layout()
        if child_layout is not None and _remove_widget_from_layout(child_layout, target):
            return True
    return False


def _center_in_overlay(widget: QWidget, overlay: QWidget) -> QPoint:
    return widget.mapTo(overlay, widget.rect().center())


def _top_left_for_center(center: QPoint, widget: QWidget) -> QPoint:
    """Return a top-left whose integer QRect.center() equals center exactly."""
    return QPoint(
        center.x() - (widget.width() - 1) // 2,
        center.y() - (widget.height() - 1) // 2,
    )


class _CardActionAligner(QObject):
    """Lock the two left utility buttons to the right action-row Y coordinates."""

    _EVENTS = {
        QEvent.Type.Show,
        QEvent.Type.Resize,
        QEvent.Type.LayoutRequest,
        QEvent.Type.PolishRequest,
    }

    def __init__(
        self,
        overlay: QWidget,
        hide_button: QToolButton,
        info_button: QToolButton,
        left_anchor: QToolButton | None,
        fourth_button: QToolButton,
        fifth_button: QToolButton,
    ) -> None:
        super().__init__(overlay)
        self.overlay = overlay
        self.hide_button = hide_button
        self.info_button = info_button
        self.left_anchor = left_anchor
        self.fourth_button = fourth_button
        self.fifth_button = fifth_button
        overlay.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._EVENTS:
            QTimer.singleShot(0, self.reposition)
        return False

    def _left_center_x(self) -> int:
        if self.left_anchor is not None and self.left_anchor.isVisible():
            return _center_in_overlay(self.left_anchor, self.overlay).x()
        # Native card layout uses an 8 px inset for the action columns.
        return 8 + (self.hide_button.width() - 1) // 2

    def reposition(self) -> None:
        if not all(
            widget is not None
            for widget in (
                self.overlay,
                self.hide_button,
                self.info_button,
                self.fourth_button,
                self.fifth_button,
            )
        ):
            return

        left_x = self._left_center_x()
        fourth_center = _center_in_overlay(self.fourth_button, self.overlay)
        fifth_center = _center_in_overlay(self.fifth_button, self.overlay)

        self.hide_button.move(
            _top_left_for_center(QPoint(left_x, fourth_center.y()), self.hide_button)
        )
        self.info_button.move(
            _top_left_for_center(QPoint(left_x, fifth_center.y()), self.info_button)
        )
        self.hide_button.raise_()
        self.info_button.raise_()


def _fix_card_actions(card: Any) -> None:
    hide_button = getattr(card, "_fh6_hide_button", None)
    info_button = getattr(card, "_fh6_info_button", None)
    zoom_button = getattr(card, "_fh6_zoom_button", None)
    memo_button = getattr(card, "_fh6_memo_button", None)
    move_button = getattr(card, "_fh6_game_move_button", None)
    image_label = getattr(card, "_fh6_image_label", None)

    if not all(
        isinstance(widget, QToolButton)
        for widget in (hide_button, info_button, zoom_button, memo_button)
    ):
        return
    if image_label is None:
        return

    image_host = image_label.parentWidget()
    stack = image_host.layout() if image_host is not None else None
    overlay = stack.currentWidget() if stack is not None and hasattr(stack, "currentWidget") else None
    if not isinstance(overlay, QWidget):
        return

    # The native detail button is bottom-anchored by a stretch. In a taller
    # one-card/hidden layout this makes its gap to Hide grow. Remove it from the
    # layout and anchor both left buttons to the same Y rows as right actions 4/5.
    _remove_widget_from_layout(overlay.layout(), info_button)
    info_button.setParent(overlay)
    info_button.show()

    # Replace stateful QIcon rendering with a fixed raster geometry. Qt now only
    # changes color on toggle, so checked state cannot appear stretched.
    hide_button.setIconSize(QSize(22, 22))

    def update_hide_icon(enabled: bool) -> None:
        hide_button.setIcon(QIcon(_eye_slash_pixmap(bool(enabled), 22)))

    update_hide_icon(hide_button.isChecked())
    hide_button.toggled.connect(update_hide_icon)

    anchor = move_button if isinstance(move_button, QToolButton) else None
    aligner = _CardActionAligner(
        overlay,
        hide_button,
        info_button,
        anchor,
        zoom_button,
        memo_button,
    )
    card._fh6_card_action_aligner = aligner
    QTimer.singleShot(0, aligner.reposition)


def apply_v1_3_2_card_alignment_patch(MainWindow) -> None:
    """Keep left card actions aligned regardless of card/image-host height."""
    if getattr(MainWindow, "_fh6_v132_card_alignment_patched", False):
        return

    original_make_card = MainWindow._make_saved_content_card

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery":
            _fix_card_actions(card)
        return card

    MainWindow._make_saved_content_card = patched_make_card
    MainWindow._fh6_v132_card_alignment_patched = True
