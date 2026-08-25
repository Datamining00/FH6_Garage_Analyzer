from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLayout, QToolButton, QWidget


def _eye_slash_pixmap(active: bool, size: int = 22) -> QPixmap:
    """Draw a stable eye-slash at the same apparent scale as card action icons.

    The reference livery-info glyph occupies an 18x20 alpha footprint when Qt
    renders it into the card's 22x22 icon slot.  The eye itself stays naturally
    wide; the diagonal slash extends vertically so the combined symbol has a
    similar footprint without stretching the eye geometry. Checked/unchecked
    states differ only in color.
    """
    raw_size = 64
    raw = QPixmap(raw_size, raw_size)
    raw.fill(Qt.GlobalColor.transparent)
    painter = QPainter(raw)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = QColor("#6e4bf2" if active else "#8d93a2")
    pen = QPen(color, 5.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Keep the eye naturally horizontal. The slash is deliberately steeper and
    # taller so the combined mark occupies the same visual height as the native
    # information glyph without non-uniform scaling.
    path = QPainterPath()
    path.moveTo(7.0, raw_size / 2)
    path.cubicTo(17.0, 20.0, raw_size - 17.0, 20.0, raw_size - 7.0, raw_size / 2)
    path.cubicTo(raw_size - 17.0, 44.0, 17.0, 44.0, 7.0, raw_size / 2)
    painter.drawPath(path)
    painter.drawEllipse(QRectF(raw_size / 2 - 7.0, raw_size / 2 - 7.0, 14.0, 14.0))
    painter.drawLine(17, 3, raw_size - 17, raw_size - 3)
    painter.end()

    image = raw.toImage()
    min_x = raw_size
    min_y = raw_size
    max_x = -1
    max_y = -1
    for y in range(raw_size):
        for x in range(raw_size):
            if image.pixelColor(x, y).alpha() > 0:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    if max_x < min_x or max_y < min_y:
        return result

    cropped = raw.copy(
        min_x,
        min_y,
        max_x - min_x + 1,
        max_y - min_y + 1,
    )
    target_box = QSize(
        max(1, round(size * 18 / 22)),
        max(1, round(size * 20 / 22)),
    )
    fitted = cropped.scaled(
        target_box,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    painter = QPainter(result)
    x = (size - fitted.width()) // 2
    y = (size - fitted.height()) // 2
    painter.drawPixmap(x, y, fitted)
    painter.end()
    return result


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
    return QPoint(
        center.x() - (widget.width() - 1) // 2,
        center.y() - (widget.height() - 1) // 2,
    )


class _CardActionAligner(QObject):
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

    _remove_widget_from_layout(overlay.layout(), info_button)
    info_button.setParent(overlay)
    info_button.show()

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

