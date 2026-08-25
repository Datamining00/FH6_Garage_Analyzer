from __future__ import annotations

from pathlib import Path
from datetime import datetime
from collections import Counter
import re
from typing import Optional

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPoint, QRect, QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QImage, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QTextEdit,
    QToolButton,
    QStyle,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .annotations import AnnotationStore, append_note
from .auction_card_loader import schedule_auction_cards
from .auction_registry_state import is_auction_livery_registered
from .auction_ui_safety import is_auction_livery
from .card_metadata_layout import _compact_window_chrome, _configure_card_metadata
from .card_action_alignment import _fix_card_actions
from .card_state_sync import (
    _refresh_dialog_memo_button,
    _sync_cached_annotation_card,
    _sync_cached_hidden_card,
)
from .card_visuals import _fix_busy_overlay, _normalize_card_actions
from .change_dialog_cards import _repair_card_actions
from .car_db import CarDatabase, CarDatabaseError, REMOTE_SOURCE_PAGE
from .game_navigation import (
    GameGridSession,
    GameNavigationError,
    NavigationItem,
    send_arrow_keys_to_fh6,
)
from .i18n import SUPPORTED_LANGUAGES, get_language, normalize_language, tr
from .models import LiveryRecord, ScanResult, TuningRecord
from .livery_visibility import (
    AUCTION_APPLIED_MODE,
    AUCTION_UNAPPLIED_MODE,
    HIDDEN_MODE,
    eye_slash_pixmap,
    install_visibility_filter_rows,
    is_unapplied_auction_livery,
    is_livery_hidden,
    set_livery_hidden,
    visibility_labels,
)
from .preferences import LocalPreferences
from .refresh_diff_service import update_livery_refresh_diff
from .scanner import SaveLayoutError, scan_save
from .scan_result_processing import populate_scan_result_ui
from .saved_content_cards import (
    _delete_cached_cards,
    _ensure_scan_generation,
    _populate_livery_grid_reusing_cards,
    _populate_tuning_grid_reusing_cards,
    initialize_ui_performance_state,
)
from .saved_content_presenter import (
    FilterState,
    build_grid_sections,
    build_search_text,
    filter_matches,
    search_matches,
)
from .saved_content_view import (
    SortSpec,
    sort_records,
    vehicle_brand_sort_key,
)
from .tune_data import TuneDataError, read_tune_data
from .thumbnail_display import _configure_aspect_card, _load_original_pixmap
from .ui_responsiveness import (
    _livery_visibility_allowed,
    _responsive_clear_grid_layout,
    _schedule_grid_followup,
    _yield_busy_events,
)
from .ui_cleanup import _install_card_hide_button
from .view_operations import ViewOperationCoordinator
from .window_responsiveness import (
    _ensure_resize_timer,
    _finalize_resize,
    _lightweight_reflow,
    _optimized_sync_grid_widths,
    _restore_window_geometry,
    _save_window_geometry,
    _schedule_resize_settle,
)


APP_STYLE = """
QMainWindow { background: #f7f8fb; color: #171924; font-family: 'Segoe UI Variable', 'Segoe UI'; font-size: 10pt; }
QWidget { color: #171924; font-family: 'Segoe UI Variable', 'Segoe UI'; font-size: 10pt; }
QLabel { background: transparent; }
QFrame#sidebar { background: #171821; border: none; }
QLabel#brand { color: white; font-size: 15pt; font-weight: 700; padding: 8px 4px 18px 4px; }
QPushButton#nav { color: #c7c9d4; background: transparent; border: 0; padding: 11px 14px; text-align: left; border-radius: 8px; }
QPushButton#nav:hover { background: #242632; color: white; }
QPushButton#nav:checked { background: #6e4bf2; color: white; font-weight: 600; }
QFrame#card, QFrame#panel { background: white; border: 1px solid #e7e8ee; border-radius: 12px; }
QLabel#cardTitle { color: #6c7080; font-size: 9pt; }
QLabel#cardValue { color: #171924; font-size: 22pt; font-weight: 700; }
QLabel#pageTitle { font-size: 18pt; font-weight: 700; }
QLabel#muted { color: #737787; }
QLabel#badge { background: #eee9ff; color: #5f39d8; padding: 4px 8px; border-radius: 8px; font-weight: 600; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #dfe1e8; border-radius: 8px; padding: 6px 9px; }
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #8c74ee; }
QPushButton#primary { background: #6e4bf2; color: white; border: 0; border-radius: 8px; padding: 9px 14px; font-weight: 600; }
QPushButton#secondary { background: white; color: #303341; border: 1px solid #dfe1e8; border-radius: 8px; padding: 8px 12px; }
QPushButton#secondary:hover { border-color: #9c8cf5; }
QPushButton#secondary:checked { background: #eee9ff; color: #5f39d8; border-color: #8c74ee; font-weight: 600; }
QTableWidget { background: white; border: 0; gridline-color: #eceef3; selection-background-color: #f0ecff; selection-color: #171924; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #eff0f4; }
QHeaderView::section { background: #fafbfc; color: #6c7080; border: 0; border-bottom: 1px solid #e9eaf0; padding: 8px; font-weight: 600; }
QTextEdit { background: #111218; color: #d9dbe5; border: 0; border-radius: 10px; padding: 10px; font-family: Consolas; }
QDialog { background: #f7f8fb; }
QMenu { background:#ffffff; color:#20232d; border:1px solid #d9dce5; border-radius:8px; padding:5px; }
QMenu::item { background:transparent; color:#20232d; padding:8px 24px 8px 12px; border-radius:5px; }
QMenu::item:selected { background:#eee9ff; color:#5335c7; }
QMenu::item:checked { background:#eee9ff; color:#5335c7; border:1px solid #d8ceff; }
QMenu::indicator { width:0px; height:0px; }
QMenu::item:disabled { color:#989ca8; }
QMenu::separator { height:1px; background:#e5e7ec; margin:5px 7px; }
QScrollBar:vertical { background:#eef0f5; width:10px; margin:3px 1px; border:0; border-radius:5px; }
QScrollBar::handle:vertical { background:#b8aecf; min-height:42px; border-radius:4px; }
QScrollBar::handle:vertical:hover { background:#8c74ee; }
QScrollBar::handle:vertical:pressed { background:#6e4bf2; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; border:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QMessageBox { background: #f7f8fb; }
QMessageBox QLabel { color: #171924; background: transparent; font-size: 10pt; }
QMessageBox QPushButton {
    min-width: 76px; min-height: 30px; padding: 3px 12px;
    background: white; color: #171924;
    border: 1px solid #cfd3dd; border-radius: 6px;
}
QMessageBox QPushButton:hover { background: #f2efff; border-color: #8c74ee; }
QMessageBox QPushButton:default { background: #6e4bf2; color: white; border-color: #6e4bf2; }
QMessageBox QPushButton:disabled { color: #8b8f9c; background: #eceef2; border-color: #d7dae2; }
"""


def _classification_pixmap(kind: str, active: bool, size: int = 24) -> QPixmap:
    """Draw the exact active/inactive glyph shared by cards and filters."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    colors = {
        "check": (QColor("#20a653"), QColor("#9ba5b3")),
        "triangle": (QColor("#d98216"), QColor("#9ba5b3")),
        "excluded": (QColor("#df3545"), QColor("#9ba5b3")),
        "memo": (QColor("#7656e8"), QColor("#9ba5b3")),
        "duplicate": (QColor("#5f39d8"), QColor("#9ba5b3")),
        "info": (QColor("#6e4bf2"), QColor("#9ba5b3")),
        "livery_info": (QColor("#6e4bf2"), QColor("#9ba5b3")),
        "tuning_info": (QColor("#6e4bf2"), QColor("#9ba5b3")),
        "move": (QColor("#6e4bf2"), QColor("#6e4bf2")),
        "search": (QColor("#626979"), QColor("#626979")),
    }
    color = colors.get(kind, colors["check"])[0 if active else 1]
    pen = QPen(color, 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "check":
        # Concentric marker: a ring plus a smaller centered circle.
        painter.drawEllipse(QRect(3, 3, size - 6, size - 6))
        painter.setBrush(color)
        inner = max(5, size // 4)
        offset = (size - inner) // 2
        painter.drawEllipse(QRect(offset, offset, inner, inner))
    elif kind in {"info", "livery_info"}:
        painter.drawRoundedRect(QRect(5, 3, size - 10, size - 6), 3, 3)
        painter.drawLine(8, 8, size - 8, 8)
        painter.drawLine(8, 12, size - 10, 12)
        painter.setBrush(color)
        painter.drawEllipse(QRect(size - 9, size - 9, 6, 6))
    elif kind == "tuning_info":
        for y, knob_x in ((7, 10), (12, 16), (17, 8)):
            painter.drawLine(4, y, size - 4, y)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(QRect(knob_x - 3, y - 3, 6, 6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == "move":
        painter.drawLine(5, size // 2, size - 5, size // 2)
        painter.drawLine(size - 10, 7, size - 5, size // 2)
        painter.drawLine(size - 5, size // 2, size - 10, size - 7)
    elif kind == "search":
        painter.drawEllipse(QRect(4, 4, size - 11, size - 11))
        painter.drawLine(size - 9, size - 9, size - 4, size - 4)
    elif kind == "triangle":
        points = QPolygon([QPoint(size // 2, 4), QPoint(size - 4, size - 5), QPoint(4, size - 5)])
        if active:
            painter.setBrush(color)
        painter.drawPolygon(points)
    elif kind == "excluded":
        painter.drawLine(5, 5, size - 5, size - 5)
        painter.drawLine(size - 5, 5, 5, size - 5)
    elif kind == "memo":
        painter.drawRoundedRect(QRect(5, 3, size - 10, size - 6), 2, 2)
        painter.drawLine(8, 9, size - 8, 9)
        painter.drawLine(8, 13, size - 8, 13)
        painter.drawLine(8, 17, size - 10, 17)
        if active:
            painter.setBrush(color)
            painter.drawEllipse(QRect(size - 8, 2, 6, 6))
    else:
        painter.drawRoundedRect(QRect(5, 7, size - 10, size - 10), 2, 2)
        painter.drawRoundedRect(QRect(8, 4, size - 10, size - 10), 2, 2)
    painter.end()
    return pixmap


def _classification_toggle_icon(kind: str) -> QIcon:
    icon = QIcon()
    icon.addPixmap(
        _classification_pixmap(kind, False),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    icon.addPixmap(
        _classification_pixmap(kind, True),
        QIcon.Mode.Normal,
        QIcon.State.On,
    )
    return icon


class PersistentFilterMenu(QMenu):
    """Keep checkable filter actions open so several can be selected."""

    def mouseReleaseEvent(self, event) -> None:
        action = self.actionAt(event.position().toPoint())
        if action is not None and action.isCheckable():
            # QAction.trigger() performs Qt's native check-state transition and
            # emits triggered exactly once. Manually emitting the signal left
            # the visual action and internal state out of sync on Windows.
            action.trigger()
            self.update()
            return
        super().mouseReleaseEvent(event)


class MultiStatusFilterButton(QToolButton):
    selectionChanged = Signal()

    FILTERS = (
        (1, "check", True, "status.check"),
        (5, "triangle", True, "status.triangle"),
        (7, "excluded", True, "status.excluded"),
        (10, "check", False, "status.none"),
        (3, "memo", True, "status.memo_yes"),
        (4, "memo", False, "status.memo_no"),
    )

    def __init__(self, include_duplicate: bool, parent=None) -> None:
        super().__init__(parent)
        self.setText(tr("common.filter"))
        self.setObjectName("secondaryFilterButton")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setToolTip(tr("status.filter_tip"))
        self._actions: dict[int, QPushButton] = {}
        menu = PersistentFilterMenu(self)
        menu.setToolTipsVisible(True)
        menu.setMinimumWidth(178)
        entries = list(self.FILTERS)
        if include_duplicate:
            entries.append((9, "duplicate", True, "status.duplicate_livery_only"))
        for mode, kind, active, meaning_key in entries:
            meaning = tr(meaning_key)
            label = tr("status.duplicate_livery") if mode == 9 else meaning
            row = QPushButton(label)
            row.setCheckable(True)
            row.setIcon(QIcon(_classification_pixmap(kind, active)))
            row.setIconSize(QSize(22, 22))
            row.setToolTip(meaning)
            row.setFixedHeight(36)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(
                "QPushButton { background:transparent; color:#20232d; border:1px solid transparent; "
                "border-radius:6px; padding:5px 9px; text-align:left; }"
                "QPushButton:hover { background:#f4f1ff; border-color:#e5deff; }"
                "QPushButton:checked { background:#eee9ff; color:#5335c7; "
                "border-color:#d8ceff; font-weight:600; }"
            )
            row.toggled.connect(
                lambda checked=False, m=mode:
                self._row_toggled(m, checked)
            )
            widget_action = QWidgetAction(menu)
            widget_action.setDefaultWidget(row)
            menu.addAction(widget_action)
            self._actions[mode] = row
        self.setMenu(menu)
        if include_duplicate:
            install_visibility_filter_rows(
                self,
                visibility_labels((get_language() or "ko").startswith("ko")),
            )

    def _row_toggled(self, mode: int, checked: bool) -> None:
        """Keep logically incompatible filter choices mutually exclusive."""
        if checked:
            incompatible: set[int] = set()
            if mode == 10:
                incompatible = {1, 5, 7}
            elif mode in {1, 5, 7}:
                incompatible = {10}
            elif mode == 3:
                incompatible = {4}
            elif mode == 4:
                incompatible = {3}
            elif mode == AUCTION_APPLIED_MODE:
                incompatible = {AUCTION_UNAPPLIED_MODE}
            elif mode == AUCTION_UNAPPLIED_MODE:
                incompatible = {AUCTION_APPLIED_MODE}
            for other_mode in incompatible:
                other = self._actions.get(other_mode)
                if other is not None and other.isChecked():
                    other.blockSignals(True)
                    other.setChecked(False)
                    other.blockSignals(False)
        self._changed()

    def _changed(self) -> None:
        selected = len(self.selected_modes())
        self.setText(tr("common.filter") if not selected else tr("common.filter_count", count=selected))
        self.selectionChanged.emit()

    def selected_modes(self) -> set[int]:
        return {
            mode for mode, button in self._actions.items()
            if button.isChecked()
        }

    def currentIndex(self) -> int:
        """Compatibility for annotation refresh dependency checks."""
        modes = self.selected_modes()
        return next(iter(modes)) if len(modes) == 1 else 0


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
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
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


class BusyOverlay(QWidget):
    """Blocking visual shown while a scan or synchronous rebuild is running."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background:rgba(23,24,33,145);")
        layout = QVBoxLayout(self)
        layout.addStretch(1)

        panel = QFrame()
        panel.setFixedWidth(320)
        panel.setStyleSheet(
            "QFrame { background:white; border:1px solid #dddfea; border-radius:14px; }"
            "QLabel { background:transparent; color:#20232d; border:0; font-size:11pt; font-weight:650; }"
            "QProgressBar { background:#ececf3; border:0; border-radius:4px; min-height:8px; max-height:8px; }"
            "QProgressBar::chunk { background:#6e4bf2; border-radius:4px; }"
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 21, 24, 21)
        panel_layout.setSpacing(14)
        self.message = QLabel(tr("common.processing"))
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        panel_layout.addWidget(self.message)
        panel_layout.addWidget(self.progress)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(panel)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        self.hide()



class DashboardSortBar(QWidget):
    """Stable dashboard header row with label + ▲/▼ controls.

    This is deliberately separate from QHeaderView.  The previous implementation
    placed child buttons inside the header viewport, which made text/button geometry
    depend on native header painting and caused overlap.  Here each column owns a
    normal QWidget cell and the cell widths are synchronized with the table columns.
    """

    sortRequested = Signal(int, object)

    def __init__(
        self,
        table: QTableWidget,
        labels: tuple[str, str, str, str],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._table = table
        self._labels = labels
        self._cells: list[QFrame] = []
        self._pairs: dict[int, tuple[QToolButton, QToolButton]] = {}

        self.setFixedHeight(39)
        self.setStyleSheet("background:#fafbfc; border-bottom:1px solid #e9eaf0;")

        button_style = (
            "QToolButton { background:transparent; color:#9297a7; border:0; "
            "padding:0; font-size:7pt; font-weight:700; }"
            "QToolButton:hover { color:#6e4bf2; background:#f0ebff; border-radius:4px; }"
            "QToolButton:checked { color:#6e4bf2; background:#e7dfff; border-radius:4px; }"
        )

        for section, label_text in enumerate(labels):
            cell = QFrame(self)
            cell.setStyleSheet("background:#fafbfc; border:0;")
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(8, 0, 4, 0)
            cell_layout.setSpacing(2)

            label = QLabel(label_text)
            label.setStyleSheet(
                "background:transparent; color:#6c7080; font-weight:600; border:0;"
            )
            cell_layout.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)

            up = QToolButton()
            up.setText("▲")
            up.setToolTip(tr("common.ascending", label=label_text))
            up.setAccessibleName(tr("common.ascending", label=label_text))
            up.setCheckable(True)
            up.setAutoRaise(True)
            up.setFixedSize(17, 22)
            up.setCursor(Qt.CursorShape.PointingHandCursor)
            up.setStyleSheet(button_style)
            up.clicked.connect(
                lambda _checked=False, s=section: self.sortRequested.emit(
                    s, Qt.SortOrder.AscendingOrder
                )
            )

            down = QToolButton()
            down.setText("▼")
            down.setToolTip(tr("common.descending", label=label_text))
            down.setAccessibleName(tr("common.descending", label=label_text))
            down.setCheckable(True)
            down.setAutoRaise(True)
            down.setFixedSize(17, 22)
            down.setCursor(Qt.CursorShape.PointingHandCursor)
            down.setStyleSheet(button_style)
            down.clicked.connect(
                lambda _checked=False, s=section: self.sortRequested.emit(
                    s, Qt.SortOrder.DescendingOrder
                )
            )

            cell_layout.addWidget(up, 0, Qt.AlignmentFlag.AlignVCenter)
            cell_layout.addWidget(down, 0, Qt.AlignmentFlag.AlignVCenter)
            cell_layout.addStretch(1)

            self._cells.append(cell)
            self._pairs[section] = (up, down)

        # QHeaderView remains as a geometry engine only; it is hidden visually.
        header = self._table.horizontalHeader()
        header.sectionResized.connect(lambda *_args: self._sync_geometry())
        self._table.verticalScrollBar().rangeChanged.connect(
            lambda *_args: QTimer.singleShot(0, self._sync_geometry)
        )
        QTimer.singleShot(0, self._sync_geometry)

    def set_active_sort(self, section: int, order: Qt.SortOrder) -> None:
        for idx, (up, down) in self._pairs.items():
            up.setChecked(
                idx == section and order == Qt.SortOrder.AscendingOrder
            )
            down.setChecked(
                idx == section and order == Qt.SortOrder.DescendingOrder
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_geometry)

    def _sync_geometry(self) -> None:
        x = 0
        for column, cell in enumerate(self._cells):
            width = self._table.columnWidth(column)
            # The final visual cell should use the remaining width so no blank
            # strip appears beside the table's vertical scrollbar.
            if column == len(self._cells) - 1:
                width = max(width, self.width() - x)
            cell.setGeometry(x, 0, max(1, width), self.height())
            cell.show()
            cell.raise_()
            x += width


class CopyValueLabel(QLabel):
    """A metadata label that copies only its raw value when clicked."""

    def __init__(self, prefix: str, value: str, parent: Optional[QWidget] = None):
        self.prefix = prefix
        self.copy_value = value
        super().__init__(f"{prefix}: {value}", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("common.copy_value", label=prefix))

    def setCopyValue(self, value: str) -> None:
        self.copy_value = value
        self.setText(f"{self.prefix}: {value}")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            QApplication.clipboard().setText(self.copy_value)
            window = self.window()
            if isinstance(window, MainWindow):
                window._show_copy_toast()
            elif isinstance(window, QMainWindow):
                bar = window.statusBar()
                bar.showMessage(tr("common.copied"), 1000)
                QTimer.singleShot(1000, bar.hide)
            event.accept()
            return
        super().mousePressEvent(event)


class ScanWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path, car_db: CarDatabase):
        super().__init__()
        self.path = path
        self.car_db = car_db

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(scan_save(self.path, self.car_db))
        except Exception as exc:  # keep worker errors out of the GUI event loop
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class CarDatabaseUpdateWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, cache_path: Path):
        super().__init__()
        self.cache_path = cache_path

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(CarDatabase.fetch_remote_update(self.cache_path))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class SummaryCard(QFrame):
    def __init__(self, title: str, value: str = "—", subtitle: str = ""):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        self.value = QLabel(value)
        self.value.setObjectName("cardValue")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("muted")
        self.subtitle.setVisible(bool(subtitle))
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)


class MainWindow(QMainWindow):
    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.car_db = CarDatabase(project_root / "data" / "car_names.json")
        self.settings = QSettings()
        self.annotations = AnnotationStore()
        self.local_preferences = LocalPreferences()
        # Save-related persistence is path-only. Remove the old UI-mode key from
        # v0.1.2 so no scan result, thumbnail or view state is persisted.
        self.settings.remove("livery_view_mode")
        self.result: Optional[ScanResult] = None
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._db_update_thread: Optional[QThread] = None
        self._db_update_worker: Optional[CarDatabaseUpdateWorker] = None
        self._livery_grid_cards: list[QFrame] = []
        self._livery_card_by_key: dict[str, QFrame] = {}
        self._livery_group_headers: dict[str, QLabel] = {}
        self._tuning_grid_cards: list[QFrame] = []
        self._tuning_card_by_key: dict[str, QFrame] = {}
        self._tuning_group_headers: dict[str, QLabel] = {}
        self._saved_content_action_rows: dict[str, QHBoxLayout] = {}
        # UI-only sort state. This is intentionally not persisted.
        self._livery_sort_mode = "__initial__"
        self._tuning_sort_mode = "__initial__"
        self._livery_sort_descending = False
        self._tuning_sort_descending = False
        self._status_token = 0
        self._game_navigation_sessions: dict[str, GameGridSession] = {}
        self._game_navigation_generation = 0
        self._game_navigation_pending = False
        self._busy_depth = 0
        self._fh6_busy_last_yield = 0.0
        self._fh6_busy_event_pump_active = False
        self._fh6_livery_grid_followup_pending = False
        self._fh6_tuning_grid_followup_pending = False
        self._search_debounce_timers: dict[int, QTimer] = {}

        # Dashboard defaults:
        #   vehicle mode -> Car ID ascending
        #   creator mode -> creator name ascending
        self._dashboard_car_sort_section = 0
        self._dashboard_car_sort_order = Qt.SortOrder.AscendingOrder
        self._dashboard_creator_sort_section = 1
        self._dashboard_creator_sort_order = Qt.SortOrder.AscendingOrder

        self.setWindowTitle("FH6 Assistant v1.3.1")
        self.resize(1460, 900)
        # Allow a narrower compact layout while preventing the two-row toolbar
        # and card metadata from being vertically clipped.
        self.setMinimumSize(960, 680)
        QApplication.instance().setStyleSheet(APP_STYLE)
        self._build_ui()
        _ensure_resize_timer(self)
        _restore_window_geometry(self)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._fh6_v131_save_window_geometry)
        _compact_window_chrome(self)

    def _fh6_v131_save_window_geometry(self) -> None:
        _save_window_geometry(self)

    def _fh6_v131_restore_window_geometry(self) -> bool:
        return _restore_window_geometry(self)

    def _fh6_v131_lightweight_reflow(self, content_type: str) -> bool:
        return _lightweight_reflow(self, content_type)

    def _fh6_v131_schedule_resize_settle(self) -> None:
        _schedule_resize_settle(self)

    def _fh6_v131_finalize_resize(self) -> None:
        _finalize_resize(self)
        self._busy_overlay = BusyOverlay(self)
        self._busy_overlay.setGeometry(self.rect())
        _fix_busy_overlay(self)
        self._view_operations = ViewOperationCoordinator(self)
        initialize_ui_performance_state(self)
        self._apply_pointing_cursors(self)
        self._refresh_db_status()
        self._set_always_on_top(
            self.settings.value("window_always_on_top", False, bool),
            persist=False,
        )

        last = self.settings.value("last_save_path", "", str)
        if last and Path(last).is_dir():
            self.path_edit.setText(last)
            # Persist only the path. Re-read the live save on every launch.
            QTimer.singleShot(0, lambda saved=Path(last): self.start_scan(saved))

    def _begin_busy(self, message: str | None = None) -> None:
        if message is None:
            message = tr("common.processing")
        self._busy_depth += 1
        if not hasattr(self, "_busy_overlay"):
            return
        self._busy_overlay.message.setText(message)
        self._busy_overlay.setGeometry(self.rect())
        self._busy_overlay.show()
        self._busy_overlay.raise_()
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        self._fh6_busy_last_yield = 0.0
        _yield_busy_events(self, force=True)

    def _end_busy(self) -> None:
        self._busy_depth = max(0, self._busy_depth - 1)
        if self._busy_depth == 0 and hasattr(self, "_busy_overlay"):
            self._busy_overlay.hide()

    def _keep_busy_responsive(self, index: int, interval: int = 12) -> None:
        """Let the indeterminate progress animation repaint during rebuilds."""
        _yield_busy_events(self, force=(index == 0))

    def _connect_debounced_search(
        self,
        field: QLineEdit,
        callback,
        delay_ms: int = 250,
    ) -> None:
        """Run expensive filtering once after typing pauses, or on Enter."""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(delay_ms)

        def apply_now() -> None:
            timer.stop()
            callback(field.text())

        timer.timeout.connect(apply_now)
        field.textChanged.connect(lambda _text: timer.start())
        field.returnPressed.connect(apply_now)
        self._search_debounce_timers[id(field)] = timer

    @Slot(int)
    def _on_language_preference_changed(self, index: int) -> None:
        """Persist a language choice and apply it cleanly on the next launch."""
        if index < 0:
            return
        raw_language = self.language_combo.itemData(index)
        if not isinstance(raw_language, str):
            return
        normalized = normalize_language(raw_language)
        self.settings.setValue("language", normalized)
        if normalized != get_language():
            self._show_status(tr("language.restart_required"), 6000)

    @Slot(bool)
    def _set_always_on_top(self, enabled: bool, *, persist: bool = True) -> None:
        """Apply the topmost flag without changing the current window size."""
        was_visible = self.isVisible()
        was_maximized = self.isMaximized()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if persist:
            self.settings.setValue("window_always_on_top", enabled)
        # Changing a native window flag hides an already visible window.
        if was_visible:
            self.showMaximized() if was_maximized else self.show()

    def _show_status(self, message: str, timeout: int = 0) -> None:
        """Show the status bar only while a message is active.

        Keeping an empty QStatusBar visible reserved a white strip across the
        bottom of the entire window. Timed messages now release that space.
        """
        self._status_token += 1
        token = self._status_token
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setStyleSheet(
            "QStatusBar { background:#f7f8fb; color:#555a68; "
            "border-top:1px solid #e3e5eb; padding:1px 8px; }"
        )
        bar.show()
        bar.showMessage(message)
        if timeout > 0:
            QTimer.singleShot(
                timeout,
                lambda expected=token: self._hide_status(expected),
            )

    def _hide_status(self, expected_token: int) -> None:
        if expected_token != self._status_token:
            return
        bar = self.statusBar()
        bar.clearMessage()
        bar.hide()

    def _show_copy_toast(self) -> None:
        """Show a true one-second overlay independent of mouse hover state."""
        if not hasattr(self, "_copy_toast"):
            toast = QLabel(tr("common.copied"), self)
            toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
            toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            toast.setStyleSheet(
                "QLabel { background:rgba(32,34,42,235); color:white; "
                "border-radius:8px; padding:8px 14px; font-weight:600; }"
            )
            self._copy_toast = toast
            self._copy_toast_timer = QTimer(self)
            self._copy_toast_timer.setSingleShot(True)
            self._copy_toast_timer.timeout.connect(toast.hide)

        toast = self._copy_toast
        toast.adjustSize()
        x = max(8, (self.width() - toast.width()) // 2)
        y = max(8, self.height() - toast.height() - 52)
        toast.move(x, y)
        toast.show()
        toast.raise_()
        self._copy_toast_timer.start(1000)
        self._show_status(tr("common.copied"), 1000)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(170)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 18, 15, 18)
        brand = QLabel("FH6\nASSISTANT")
        brand.setObjectName("brand")
        side.addWidget(brand)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, text in enumerate((tr("nav.dashboard"), tr("nav.livery"), tr("nav.tuning"))):
            button = QPushButton(text)
            button.setObjectName("nav")
            button.setCheckable(True)
            if index == 0:
                button.setChecked(True)
            button.clicked.connect(lambda checked=False, i=index: self.pages.setCurrentIndex(i))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch(1)

        self.language_label = QLabel(tr("language.label"))
        self.language_label.setStyleSheet(
            "color:#8d91a0; padding:0 6px 2px 6px; font-size:9pt;"
        )
        side.addWidget(self.language_label)

        self.language_combo = QComboBox()
        self.language_combo.setAccessibleName(tr("language.label"))
        for language_code, display_name in SUPPORTED_LANGUAGES.items():
            self.language_combo.addItem(display_name, language_code)
        active_language_index = self.language_combo.findData(get_language())
        if active_language_index >= 0:
            self.language_combo.setCurrentIndex(active_language_index)
        self.language_combo.setStyleSheet(
            "QComboBox { background:#242632; color:#f0f1f5; "
            "border:1px solid #343746; border-radius:7px; padding:6px 8px; }"
            "QComboBox:hover { border-color:#6e4bf2; }"
            "QComboBox::drop-down { border:0; width:22px; }"
            "QComboBox QAbstractItemView { background:#242632; color:#f0f1f5; "
            "selection-background-color:#6e4bf2; selection-color:white; }"
        )
        self.language_combo.currentIndexChanged.connect(
            self._on_language_preference_changed
        )
        side.addWidget(self.language_combo)

        self.always_on_top_box = QCheckBox(tr("sidebar.always_on_top"))
        self.always_on_top_box.setStyleSheet(
            "QCheckBox { color:#c7c9d4; spacing:7px; padding:7px 6px; }"
            "QCheckBox:hover { color:white; }"
        )
        self.always_on_top_box.setChecked(
            self.settings.value("window_always_on_top", False, bool)
        )
        self.always_on_top_box.setToolTip(
            tr("sidebar.always_on_top_tip")
        )
        self.always_on_top_box.toggled.connect(self._set_always_on_top)
        side.addWidget(self.always_on_top_box)
        version = QLabel("v1.3.1\nLIVERY & TUNING")
        version.setStyleSheet("color:#777b8b; padding:8px;")
        side.addWidget(version)
        outer.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 18)
        content_layout.setSpacing(14)

        top = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText(tr("save.placeholder"))
        choose = QPushButton(tr("save.choose_folder"))
        choose.setObjectName("primary")
        choose.clicked.connect(self.choose_save_folder)
        refresh = QPushButton(tr("save.refresh"))
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh_scan)
        top.addWidget(self.path_edit, 1)
        top.addWidget(choose)
        top.addWidget(refresh)
        content_layout.addLayout(top)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._dashboard_page())
        self.pages.addWidget(self._livery_page())
        self.pages.addWidget(self._tuning_page())
        # A scan normally completes while the dashboard page is visible.  At that
        # point the livery/tuning pages are hidden, so QWidget.isVisible() is false
        # for every card and the lazy thumbnail pass intentionally skips them.
        # Refresh again whenever a stacked page actually becomes current so the
        # first visible frame already contains its thumbnails; no resize/scroll
        # interaction should be required to trigger loading.
        self.pages.currentChanged.connect(self._on_main_page_changed)
        content_layout.addWidget(self.pages, 1)
        outer.addWidget(content, 1)

    def _page_header(self, title: str, subtitle: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("muted")
            layout.addWidget(subtitle_label)
        return layout

    def _dashboard_saved_section_header(
        self,
        title: str,
        content_type: str,
    ) -> QFrame:
        section = QFrame()
        section.setObjectName("dashboardSavedSection")
        section.setStyleSheet(
            "QFrame#dashboardSavedSection { background:#eee9ff; border:0; "
            "border-radius:6px; }"
            "QLabel { background:transparent; color:#5f39d8; font-weight:700; }"
            "QPushButton { background:#ffffff; color:#5f39d8; border:1px solid #d5c9ff; "
            "border-radius:6px; padding:3px 8px; font-size:9pt; font-weight:650; }"
            "QPushButton:hover { background:#f8f5ff; border-color:#8c74ee; }"
        )
        row = QHBoxLayout(section)
        row.setContentsMargins(9, 4, 5, 4)
        row.setSpacing(8)

        label = QLabel(title)
        row.addWidget(label)
        row.addStretch(1)

        jump_button = QPushButton(tr("dashboard.instant_move"))
        noun = (
            tr("content.noun_livery")
            if content_type == "livery"
            else tr("content.noun_tuning")
        )
        jump_button.setToolTip(
            tr("dashboard.instant_move_tip", noun=noun)
        )
        jump_button.clicked.connect(
            lambda _checked=False, kind=content_type:
            self._jump_to_dashboard_selection(kind)
        )
        row.addWidget(jump_button)
        return section

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._page_header(tr("dashboard.title"), ""))

        cards = QGridLayout()
        cards.setSpacing(12)
        self.card_cars = SummaryCard(tr("dashboard.garage_cars"), "—")
        self.card_livery = SummaryCard(tr("dashboard.saved_livery"), "—")
        self.card_tuning = SummaryCard(tr("dashboard.saved_tuning"), "—")
        for i, card in enumerate((self.card_cars, self.card_livery, self.card_tuning)):
            cards.addWidget(card, 0, i)
        layout.addLayout(cards)

        db_panel = QFrame(); db_panel.setObjectName("panel")
        db_layout = QHBoxLayout(db_panel); db_layout.setContentsMargins(14, 11, 14, 11)
        db_title = QLabel(tr("db.title"))
        db_title.setStyleSheet("font-size:11pt;font-weight:700;")

        self.db_last_update_label = QLabel(tr("db.last_update_unavailable"))
        self.db_last_update_label.setObjectName("muted")
        self.db_last_update_label.setStyleSheet(
            "color:#737787; font-size:9.5pt; background:transparent;"
        )

        self.db_update_button = QPushButton(tr("db.check_update"))
        self.db_update_button.setObjectName("secondary")
        self.db_update_button.setToolTip(tr("db.check_update_tip"))
        self.db_update_button.clicked.connect(self.start_car_db_update)

        self.db_source_button = QToolButton()
        self.db_source_button.setText(tr("db.source"))
        self.db_source_button.setIcon(self._external_link_icon())
        self.db_source_button.setIconSize(QSize(18, 18))
        self.db_source_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.db_source_button.setToolTip(tr("db.source_tip"))
        self.db_source_button.setAccessibleName(tr("db.source_accessible"))
        self.db_source_button.setMinimumHeight(38)
        self.db_source_button.setStyleSheet(
            "QToolButton { background:white; color:#303341; "
            "border:1px solid #dfe1e8; border-radius:8px; padding:5px; }"
            "QToolButton:hover { border-color:#9c8cf5; background:#f7f5ff; }"
        )
        self.db_source_button.clicked.connect(self._open_car_db_source)

        self.db_override_button = QPushButton(tr("db.override"))
        self.db_override_button.setObjectName("secondary")
        self.db_override_button.setToolTip(tr("db.override_tip"))
        self.db_override_button.clicked.connect(self.open_car_db_override)

        db_layout.addWidget(db_title)
        db_layout.addWidget(self.db_last_update_label)
        db_layout.addStretch(1)
        db_layout.addWidget(self.db_override_button)
        db_layout.addWidget(self.db_update_button)
        db_layout.addWidget(self.db_source_button)
        layout.addWidget(db_panel)

        body = QHBoxLayout()
        left = QFrame(); left.setObjectName("panel")
        left_l = QVBoxLayout(left); left_l.setContentsMargins(14, 14, 14, 14)
        dashboard_controls = QGridLayout()
        dashboard_controls.setHorizontalSpacing(7)
        dashboard_controls.setVerticalSpacing(7)

        # Dashboard aggregation selector.  Vehicle aggregation remains the default,
        # while creator aggregation summarizes custom liveries and saved tunings.
        self.dashboard_mode_group = QButtonGroup(self)
        self.dashboard_mode_group.setExclusive(True)

        self.dashboard_car_button = QPushButton(tr("dashboard.by_vehicle"))
        self.dashboard_car_button.setObjectName("secondary")
        self.dashboard_car_button.setCheckable(True)
        self.dashboard_car_button.setChecked(True)
        self.dashboard_car_button.clicked.connect(lambda _checked=False: self._set_dashboard_content_mode(0))

        self.dashboard_creator_button = QPushButton(tr("dashboard.by_creator"))
        self.dashboard_creator_button.setObjectName("secondary")
        self.dashboard_creator_button.setCheckable(True)
        self.dashboard_creator_button.clicked.connect(lambda _checked=False: self._set_dashboard_content_mode(1))

        self.dashboard_mode_group.addButton(self.dashboard_car_button)
        self.dashboard_mode_group.addButton(self.dashboard_creator_button)

        self.car_search = QLineEdit()
        self.car_search.setPlaceholderText(tr("dashboard.search_vehicle"))
        self.car_search.setMinimumWidth(0)
        self.car_search.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._connect_debounced_search(
            self.car_search,
            self._filter_dashboard_table,
        )

        # Keep the mode selectors on their own compact row and let the search
        # field use the full panel width below. This avoids English text forcing
        # the minimum window wider than the declared 960 px compact layout.
        dashboard_controls.addWidget(self.dashboard_car_button, 0, 0)
        dashboard_controls.addWidget(self.dashboard_creator_button, 0, 1)
        dashboard_controls.setColumnStretch(2, 1)
        dashboard_controls.addWidget(self.car_search, 1, 0, 1, 3)
        left_l.addLayout(dashboard_controls)

        self.dashboard_content_stack = QStackedWidget()

        self.car_table = self._table((tr("table.car_id"), tr("table.vehicle"), tr("table.livery"), tr("table.tuning")))
        self.car_table.itemSelectionChanged.connect(self._update_selected_car)
        self._configure_dashboard_table(self.car_table)

        self.car_sort_bar = DashboardSortBar(
            self.car_table,
            (tr("table.car_id"), tr("table.vehicle"), tr("table.livery"), tr("table.tuning")),
        )
        self.car_sort_bar.sortRequested.connect(self._sort_car_dashboard)
        self.car_sort_bar.set_active_sort(
            self._dashboard_car_sort_section,
            self._dashboard_car_sort_order,
        )

        car_pane = QWidget()
        car_pane_layout = QVBoxLayout(car_pane)
        car_pane_layout.setContentsMargins(0, 0, 0, 0)
        car_pane_layout.setSpacing(0)
        car_pane_layout.addWidget(self.car_sort_bar)
        car_pane_layout.addWidget(self.car_table, 1)
        self.dashboard_content_stack.addWidget(car_pane)

        # Exactly the same column geometry in creator mode:
        #   Car ID -> 합계 / 차량 -> 제작자명 / 리버리 -> 리버리 / 튜닝 -> 튜닝
        self.creator_table = self._table((tr("table.total"), tr("table.creator"), tr("table.livery"), tr("table.tuning")))
        self.creator_table.itemSelectionChanged.connect(self._update_selected_creator)
        self._configure_dashboard_table(self.creator_table)

        self.creator_sort_bar = DashboardSortBar(
            self.creator_table,
            (tr("table.total"), tr("table.creator"), tr("table.livery"), tr("table.tuning")),
        )
        self.creator_sort_bar.sortRequested.connect(self._sort_creator_dashboard)
        self.creator_sort_bar.set_active_sort(
            self._dashboard_creator_sort_section,
            self._dashboard_creator_sort_order,
        )

        creator_pane = QWidget()
        creator_pane_layout = QVBoxLayout(creator_pane)
        creator_pane_layout.setContentsMargins(0, 0, 0, 0)
        creator_pane_layout.setSpacing(0)
        creator_pane_layout.addWidget(self.creator_sort_bar)
        creator_pane_layout.addWidget(self.creator_table, 1)
        self.dashboard_content_stack.addWidget(creator_pane)

        left_l.addWidget(self.dashboard_content_stack)

        right = QFrame(); right.setObjectName("panel")
        # The detail tables need enough horizontal room for Livery/Creator and
        # Name/Creator/Size headers even at the 960 px minimum window width.
        right.setMinimumWidth(280)
        right_l = QVBoxLayout(right); right_l.setContentsMargins(14, 14, 14, 14)
        self.selected_title = QLabel(tr("dashboard.select_vehicle"))
        self.selected_title.setStyleSheet("font-size:13pt;font-weight:700;")
        self.selected_hint = QLabel("")
        self.selected_hint.setWordWrap(True); self.selected_hint.setObjectName("muted")
        self.selected_hint.hide()
        right_l.addWidget(self.selected_title)
        right_l.addWidget(self.selected_hint)

        self.saved_livery_section = self._dashboard_saved_section_header(
            tr("dashboard.saved_livery"),
            "livery",
        )
        right_l.addWidget(self.saved_livery_section)

        self.selected_liveries = self._table(("", tr("table.livery_name"), tr("table.creator_short")))
        right_l.addWidget(self.selected_liveries, 1)

        self.saved_tuning_section = self._dashboard_saved_section_header(
            tr("dashboard.saved_tuning"),
            "tuning",
        )
        right_l.addWidget(self.saved_tuning_section)

        self.selected_tunings = self._table(("", tr("table.name"), tr("table.creator_short"), tr("table.size")))
        right_l.addWidget(self.selected_tunings, 1)

        body.addWidget(left, 5)
        body.addWidget(right, 4)
        layout.addLayout(body, 1)
        return page

    def _livery_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._page_header(tr("dashboard.saved_livery"), ""))

        (
            controls,
            self.livery_search,
            self.livery_check_filter,
            self.livery_sort_group,
            self.livery_sort_buttons,
        ) = self._build_saved_content_controls("livery")
        layout.addLayout(controls)

        self.livery_table = self._saved_content_table(tr("table.livery_name"))
        self.livery_table.setParent(page)
        self.livery_table.hide()

        self.livery_grid_scroll = QScrollArea()
        self.livery_grid_scroll.setObjectName("liveryGridScroll")
        self.livery_grid_scroll.setWidgetResizable(True)
        self.livery_grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Grid cards must always fit the actual viewport. A horizontal scrollbar
        # was a symptom of the two cards' minimum-size hints exceeding the
        # available width and made the right-hand card look clipped.
        self.livery_grid_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.livery_grid_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.livery_grid_scroll.setStyleSheet(
            "QScrollArea#liveryGridScroll { background:#f7f8fb; border:0; }"
        )

        viewport = self.livery_grid_scroll.viewport()
        viewport.setObjectName("liveryGridViewport")
        viewport.setStyleSheet(
            "QWidget#liveryGridViewport { background:#f7f8fb; }"
        )

        self.livery_grid_host = QWidget()
        self.livery_grid_host.setObjectName("liveryGridHost")
        self.livery_grid_host.setMinimumWidth(0)
        self.livery_grid_host.setStyleSheet(
            "QWidget#liveryGridHost { background:#f7f8fb; }"
        )
        self.livery_grid_layout = QGridLayout(self.livery_grid_host)
        self.livery_grid_layout.setContentsMargins(2, 2, 2, 2)
        self.livery_grid_layout.setHorizontalSpacing(14)
        self.livery_grid_layout.setVerticalSpacing(14)
        self.livery_grid_layout.setColumnStretch(0, 1)
        self.livery_grid_layout.setColumnStretch(1, 1)
        self.livery_grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.livery_grid_scroll.setWidget(self.livery_grid_host)
        self.livery_grid_scroll.verticalScrollBar().valueChanged.connect(
            self._schedule_visible_livery_thumbnails
        )
        self.livery_grid_scroll.verticalScrollBar().rangeChanged.connect(
            lambda *_args: self._sync_livery_grid_card_widths()
        )

        # Receive the actual viewport's resize event during live Windows border
        # dragging.  This is synchronous and does not wait for a timer tick.
        self.livery_grid_scroll.viewport().installEventFilter(self)

        layout.addWidget(self.livery_grid_scroll, 1)
        return page

    def _tuning_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(
            self._page_header(
                tr("dashboard.saved_tuning"),
                "",
            )
        )

        (
            controls,
            self.tuning_search,
            self.tuning_check_filter,
            self.tuning_sort_group,
            self.tuning_sort_buttons,
        ) = self._build_saved_content_controls("tuning")
        layout.addLayout(controls)
        self.tuning_table = self._saved_content_table(tr("table.tuning_name"))
        self.tuning_table.setParent(page)
        self.tuning_table.hide()

        self.tuning_grid_scroll = QScrollArea()
        self.tuning_grid_scroll.setObjectName("tuningGridScroll")
        self.tuning_grid_scroll.setWidgetResizable(True)
        self.tuning_grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tuning_grid_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tuning_grid_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.tuning_grid_scroll.setStyleSheet(
            "QScrollArea#tuningGridScroll { background:#f7f8fb; border:0; }"
        )
        tuning_viewport = self.tuning_grid_scroll.viewport()
        tuning_viewport.setObjectName("tuningGridViewport")
        tuning_viewport.setStyleSheet(
            "QWidget#tuningGridViewport { background:#f7f8fb; }"
        )
        self.tuning_grid_host = QWidget()
        self.tuning_grid_host.setObjectName("tuningGridHost")
        self.tuning_grid_host.setMinimumWidth(0)
        self.tuning_grid_host.setStyleSheet(
            "QWidget#tuningGridHost { background:#f7f8fb; }"
        )
        self.tuning_grid_layout = QGridLayout(self.tuning_grid_host)
        self.tuning_grid_layout.setContentsMargins(2, 2, 2, 2)
        self.tuning_grid_layout.setHorizontalSpacing(14)
        self.tuning_grid_layout.setVerticalSpacing(14)
        self.tuning_grid_layout.setColumnStretch(0, 1)
        self.tuning_grid_layout.setColumnStretch(1, 1)
        self.tuning_grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.tuning_grid_scroll.setWidget(self.tuning_grid_host)
        self.tuning_grid_scroll.verticalScrollBar().valueChanged.connect(
            self._schedule_visible_tuning_thumbnails
        )
        self.tuning_grid_scroll.verticalScrollBar().rangeChanged.connect(
            lambda *_args: self._sync_tuning_grid_card_widths()
        )
        self.tuning_grid_scroll.viewport().installEventFilter(self)
        layout.addWidget(self.tuning_grid_scroll, 1)
        return page

    def _table(self, headers: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setIconSize(QSize(76, 48))
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for col in range(len(headers)):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        if len(headers) > 1:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return table

    def _saved_content_table(self, name_header: str) -> QTableWidget:
        """Create the common list component used by Livery and Tuning.

        Visible columns intentionally stay identical:
        Status | Vehicle | Creator | Name | Description | Memo | Created | Downloaded

        The future detail column is deliberately omitted until the supporting
        database/schema mapping is available.
        """
        table = self._table(
            (
                tr("table.status"),
                tr("table.vehicle_name"),
                tr("table.creator_short"),
                name_header,
                tr("table.description"),
                tr("table.memo"),
                tr("table.created"),
                tr("table.downloaded"),
            )
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setStyleSheet(
            "QTableWidget::item:selected { background:#f2edff; color:#171924; border:0; }"
            "QTableWidget::item:selected:active { background:#f2edff; color:#171924; border:0; }"
            "QTableWidget::item:hover { background:#fbf9ff; }"
        )

        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(0, 126)
        table.setColumnWidth(2, 150)
        table.setColumnWidth(5, 48)
        table.setColumnWidth(6, 104)
        table.setColumnWidth(7, 150)
        return table

    def _build_saved_content_controls(
        self,
        content_type: str,
    ) -> tuple[
        QVBoxLayout,
        QLineEdit,
        MultiStatusFilterButton,
        QButtonGroup,
        dict[str, QPushButton],
    ]:
        """Create two toolbar rows: search/filter, then sort/view/actions."""
        controls = QVBoxLayout()
        controls.setSpacing(7)
        search_row = QHBoxLayout()
        action_row = QHBoxLayout()
        action_row.setSpacing(7)
        self._saved_content_action_rows[content_type] = action_row

        search = QLineEdit()
        search.setPlaceholderText(
            tr("content.search_placeholder")
        )
        self._connect_debounced_search(
            search,
            lambda text, kind=content_type:
            self._request_saved_content_filter(kind, text),
        )
        search_row.addWidget(search, 1)

        status_filter = MultiStatusFilterButton(content_type == "livery", self)
        status_filter.selectionChanged.connect(
            lambda kind=content_type, field=search:
            self._request_saved_content_filter(kind, field.text())
        )
        search_row.addWidget(status_filter)
        controls.addLayout(search_row)

        sort_label = QLabel(tr("content.sort_label"))
        sort_label.setObjectName("muted")
        action_row.addWidget(sort_label)

        sort_group = QButtonGroup(self)
        sort_group.setExclusive(True)
        sort_buttons: dict[str, QPushButton] = {}

        for mode, label_text in (
            ("default", tr("content.sort_default")),
            ("brand", tr("content.sort_brand")),
            ("creator", tr("content.sort_creator")),
            ("download", tr("content.sort_download")),
        ):
            button = QPushButton(label_text)
            button.setObjectName("secondary")
            button.setCheckable(True)
            if mode == "default":
                button.setChecked(True)
            button.clicked.connect(
                lambda _checked=False, kind=content_type, m=mode:
                self._set_saved_content_sort_mode(kind, m)
            )
            sort_group.addButton(button)
            sort_buttons[mode] = button
            action_row.addWidget(button)

        separator = QLabel("││")
        separator.setObjectName("sortGroupSeparator")
        separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        separator.setStyleSheet(
            "color:#b1a8c9; font-weight:700; padding:0 2px;"
        )
        action_row.addWidget(separator)

        group_button = QPushButton(tr("content.group_vehicle"))
        group_button.setObjectName("secondary")
        group_button.setCheckable(True)
        group_button.setChecked(
            self.local_preferences.get_bool(
                f"{content_type}_group_by_vehicle",
                False,
            )
        )
        group_button.setToolTip(
            tr("content.group_vehicle_tip")
        )
        group_button.toggled.connect(
            lambda checked, kind=content_type:
            self._set_vehicle_grouping(kind, checked)
        )
        setattr(self, f"{content_type}_group_button", group_button)
        action_row.addWidget(group_button)

        creator_group_button = QPushButton(tr("content.group_creator"))
        creator_group_button.setObjectName("secondary")
        creator_group_button.setCheckable(True)
        creator_group_button.setChecked(
            self.local_preferences.get_bool(
                f"{content_type}_group_by_creator",
                False,
            )
        )
        if group_button.isChecked() and creator_group_button.isChecked():
            creator_group_button.setChecked(False)
            self.local_preferences.set_bool(
                f"{content_type}_group_by_creator",
                False,
            )
        creator_group_button.setToolTip(
            tr("content.group_creator_tip")
        )
        creator_group_button.toggled.connect(
            lambda checked, kind=content_type:
            self._set_creator_grouping(kind, checked)
        )
        setattr(
            self,
            f"{content_type}_creator_group_button",
            creator_group_button,
        )
        action_row.addWidget(creator_group_button)

        action_row.addStretch(1)
        controls.addLayout(action_row)

        return (
            controls,
            search,
            status_filter,
            sort_group,
            sort_buttons,
        )

    @Slot(str, bool)
    def _set_vehicle_grouping(
        self,
        content_type: str,
        enabled: bool,
    ) -> None:
        self.local_preferences.set_bool(
            f"{content_type}_group_by_vehicle",
            enabled,
        )
        if enabled:
            other = getattr(
                self,
                f"{content_type}_creator_group_button",
                None,
            )
            if other is not None and other.isChecked():
                other.blockSignals(True)
                other.setChecked(False)
                other.blockSignals(False)
                self.local_preferences.set_bool(
                    f"{content_type}_group_by_creator",
                    False,
                )
        search = (
            self.livery_search
            if content_type == "livery"
            else self.tuning_search
        )
        if self.result is None:
            return
        noun = (
            tr("content.noun_livery")
            if content_type == "livery"
            else tr("content.noun_tuning")
        )
        message = tr(
            "content.grouping_vehicle" if enabled else "content.relayout",
            noun=noun,
        )
        text = search.text()
        self._view_operations.request(
            content_type,
            message,
            lambda: self._filter_saved_content_views(
                content_type,
                text,
                preserve_scroll=True,
            ),
        )

    @Slot(str, bool)
    def _set_creator_grouping(
        self,
        content_type: str,
        enabled: bool,
    ) -> None:
        self.local_preferences.set_bool(
            f"{content_type}_group_by_creator",
            enabled,
        )
        if enabled:
            other = getattr(self, f"{content_type}_group_button", None)
            if other is not None and other.isChecked():
                other.blockSignals(True)
                other.setChecked(False)
                other.blockSignals(False)
                self.local_preferences.set_bool(
                    f"{content_type}_group_by_vehicle",
                    False,
                )
        search = (
            self.livery_search
            if content_type == "livery"
            else self.tuning_search
        )
        if self.result is None:
            return
        noun = (
            tr("content.noun_livery")
            if content_type == "livery"
            else tr("content.noun_tuning")
        )
        message = tr(
            "content.grouping_creator" if enabled else "content.relayout",
            noun=noun,
        )
        text = search.text()
        self._view_operations.request(
            content_type,
            message,
            lambda: self._filter_saved_content_views(
                content_type,
                text,
                preserve_scroll=True,
            ),
        )

    @Slot()
    def choose_save_folder(self) -> None:
        start = self.path_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, tr("save.folder_dialog"), start)
        if path:
            self.path_edit.setText(path)
            self.settings.setValue("last_save_path", path)
            self.start_scan(Path(path))

    @Slot()
    def refresh_scan(self) -> None:
        self.car_db.reload()
        self._refresh_db_status()
        if self.path_edit.text():
            self.start_scan(Path(self.path_edit.text()))

    def start_scan(self, path: Path) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self._view_operations.cancel_pending()
        self._begin_busy(tr("scan.loading"))
        self._show_status(tr("scan.scanning"))
        thread = QThread(self)
        worker = ScanWorker(path, self.car_db)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._scan_finished)
        worker.failed.connect(self._scan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.finished.connect(self._scan_cleanup)
        thread.start()


    @Slot()
    def _scan_cleanup(self) -> None:
        self._scan_thread = None
        self._scan_worker = None

    @Slot(object)
    def _scan_finished(self, result: ScanResult) -> None:
        try:
            self.result = result
            self._reset_game_navigation_sessions()
            self._populate_all()
        finally:
            self._end_busy()
        self._show_status(tr("scan.complete", liveries=sum(x.kind == "Livery" for x in result.liveries), tunings=len(result.tunings)), 8000)

    @Slot(str)
    def _scan_failed(self, message: str) -> None:
        self._end_busy()
        self._show_status(tr("scan.failed"), 5000)
        QMessageBox.critical(self, tr("scan.failed_title"), message)

    def _populate_all(self) -> None:
        update_livery_refresh_diff(self)
        populate_scan_result_ui(self, self._populate_all_content)
        from .release_layout import _compact_change_banner

        _compact_change_banner(self)

    def _populate_all_content(self) -> None:
        _ensure_scan_generation(self)
        assert self.result is not None
        r = self.result
        meta = r.metadata
        self.card_cars.value.setText(str(meta.reported_car_count) if meta.reported_car_count is not None else "—")
        custom = sum(1 for x in r.liveries if x.kind == "Livery")
        self.card_livery.value.setText(str(custom))
        self.card_tuning.value.setText(str(len(r.tunings)))
        self._populate_car_table()
        self._populate_creator_table()
        self._begin_busy(tr("content.rebuilding_livery"))
        try:
            self._populate_livery_table()
        finally:
            self._end_busy()
        self._populate_tuning_table()
        self._refresh_db_status(self._current_unknown_car_ids())

    def _configure_dashboard_table(self, table: QTableWidget) -> None:
        """Shared four-column dashboard geometry.

        The native horizontal header is hidden.  DashboardSortBar is the only
        visible header, eliminating native-header/button overlap completely.
        """
        header = table.horizontalHeader()
        header.setVisible(False)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(0, 92)
        table.setColumnWidth(2, 92)
        table.setColumnWidth(3, 92)


    @staticmethod
    def _order_key(value: object) -> object:
        if isinstance(value, str):
            return value.casefold()
        return value

    def _car_dashboard_sort_key(self, summary) -> tuple:
        section = self._dashboard_car_sort_section
        if section == 0:
            return (summary.car_id,)

        if section == 1:
            info = self.car_db.get(summary.car_id)
            label = (info.label or summary.label or "").strip()
            unknown = label.startswith("Car ID ")
            manufacturer = (info.manufacturer or "").strip()

            # Fallback for community/override labels such as
            # "1969 Toyota 2000 GT": year is ignored; manufacturer is Toyota.
            if not manufacturer:
                parts = label.split()
                if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 4:
                    manufacturer = parts[1]
                elif parts:
                    manufacturer = parts[0]

            return (
                1 if unknown else 0,
                manufacturer.casefold(),
                re.sub(r"^\d{4}\s+", "", label).casefold(),
                summary.car_id,
            )

        if section == 2:
            return (summary.livery_count, summary.car_id)
        if section == 3:
            return (summary.tuning_count, summary.car_id)
        return (summary.car_id,)

    def _creator_dashboard_sort_key(self, row: tuple[str, int, int]) -> tuple:
        creator, livery_count, tuning_count = row
        total = livery_count + tuning_count
        section = self._dashboard_creator_sort_section
        if section == 0:
            return (total, creator.casefold())
        if section == 1:
            return (creator == tr("creator.none"), creator.casefold())
        if section == 2:
            return (livery_count, creator.casefold())
        if section == 3:
            return (tuning_count, creator.casefold())
        return (creator.casefold(),)

    @staticmethod
    def _force_table_top(table: QTableWidget) -> None:
        """Force the viewport to row 0 after Qt completes selection/layout work."""
        def move_top() -> None:
            table.scrollToTop()
            table.verticalScrollBar().setValue(
                table.verticalScrollBar().minimum()
            )

        move_top()
        QTimer.singleShot(0, move_top)
        QTimer.singleShot(40, move_top)

    @Slot(int, object)
    def _sort_car_dashboard(self, section: int, order: Qt.SortOrder) -> None:
        self._begin_busy(tr("dashboard.sorting_vehicles"))
        try:
            self._dashboard_car_sort_section = int(section)
            self._dashboard_car_sort_order = order
            self.car_sort_bar.set_active_sort(section, order)
            self._populate_car_table()
            self._filter_dashboard_table(self.car_search.text())
            self._force_table_top(self.car_table)
        finally:
            self._end_busy()

    @Slot(int, object)
    def _sort_creator_dashboard(self, section: int, order: Qt.SortOrder) -> None:
        self._begin_busy(tr("dashboard.sorting_creators"))
        try:
            self._dashboard_creator_sort_section = int(section)
            self._dashboard_creator_sort_order = order
            self.creator_sort_bar.set_active_sort(section, order)
            self._populate_creator_table()
            self._filter_dashboard_table(self.car_search.text())
            self._force_table_top(self.creator_table)
        finally:
            self._end_busy()

    def _populate_car_table(self) -> None:
        table = self.car_table
        selected_id: Optional[int] = None
        selected_rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if selected_rows:
            item = table.item(selected_rows[0].row(), 0)
            if item:
                try:
                    selected_id = int(item.data(Qt.ItemDataRole.UserRole))
                except (TypeError, ValueError):
                    selected_id = None

        table.setRowCount(0)
        if not self.result:
            return

        rows = sorted(self.result.car_summaries, key=self._car_dashboard_sort_key)
        if self._dashboard_car_sort_order == Qt.SortOrder.DescendingOrder:
            rows.reverse()

        selected_row = -1
        for summary in rows:
            row = table.rowCount()
            table.insertRow(row)
            values = (
                summary.car_id,
                summary.label,
                summary.livery_count,
                summary.tuning_count,
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, summary.car_id)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                table.setItem(row, col, item)
            if selected_id == summary.car_id:
                selected_row = row

        if selected_row >= 0:
            table.selectRow(selected_row)
        elif table.rowCount():
            table.selectRow(0)

        if hasattr(self, "car_sort_bar"):
            self.car_sort_bar.set_active_sort(
                self._dashboard_car_sort_section,
                self._dashboard_car_sort_order,
            )

    def _creator_content_stats(self) -> list[tuple[str, int, int]]:
        """Return creator -> custom-livery/tuning counts.

        Creator matching is case-insensitive, while the first non-empty display
        spelling encountered is preserved for presentation.
        """
        if not self.result:
            return []

        stats: dict[str, dict[str, object]] = {}

        def ensure_creator(raw_name: str) -> dict[str, object]:
            display = (raw_name or "").strip() or tr("creator.none")
            key = display.casefold()
            bucket = stats.get(key)
            if bucket is None:
                bucket = {"name": display, "livery": 0, "tuning": 0}
                stats[key] = bucket
            elif bucket["name"] == tr("creator.none") and display != tr("creator.none"):
                bucket["name"] = display
            return bucket

        for record in self.result.liveries:
            if record.kind != "Livery":
                continue
            bucket = ensure_creator(record.header.creator or "")
            bucket["livery"] = int(bucket["livery"]) + 1

        for record in self.result.tunings:
            bucket = ensure_creator(record.header.creator or "")
            bucket["tuning"] = int(bucket["tuning"]) + 1

        rows = [
            (str(bucket["name"]), int(bucket["livery"]), int(bucket["tuning"]))
            for bucket in stats.values()
        ]
        rows.sort(key=lambda row: (row[0] == tr("creator.none"), row[0].casefold()))
        return rows

    def _populate_creator_table(self) -> None:
        table = self.creator_table
        selected_creator = ""
        selected_rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if selected_rows:
            item = table.item(selected_rows[0].row(), 1)
            if item:
                selected_creator = str(item.data(Qt.ItemDataRole.UserRole) or item.text())

        table.setRowCount(0)

        rows = sorted(self._creator_content_stats(), key=self._creator_dashboard_sort_key)
        if self._dashboard_creator_sort_order == Qt.SortOrder.DescendingOrder:
            rows.reverse()

        selected_row = -1
        for creator, livery_count, tuning_count in rows:
            row = table.rowCount()
            table.insertRow(row)
            total = livery_count + tuning_count
            for col, value in enumerate((total, creator, livery_count, tuning_count)):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, creator)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                table.setItem(row, col, item)
            if selected_creator and creator.casefold() == selected_creator.casefold():
                selected_row = row

        if selected_row >= 0:
            table.selectRow(selected_row)
        elif table.rowCount():
            table.selectRow(0)

        if hasattr(self, "creator_sort_bar"):
            self.creator_sort_bar.set_active_sort(
                self._dashboard_creator_sort_section,
                self._dashboard_creator_sort_order,
            )

    def _custom_liveries(self) -> list[LiveryRecord]:
        if not self.result:
            return []
        return [record for record in self.result.liveries if record.kind == "Livery"]

    def _vehicle_brand_sort_key(
        self,
        record: LiveryRecord | TuningRecord,
    ) -> tuple:
        """Sort saved content by manufacturer-first vehicle display text."""
        return vehicle_brand_sort_key(record, self._car_label)

    def _saved_content_records(
        self,
        content_type: str,
    ) -> list[LiveryRecord | TuningRecord]:
        if not self.result:
            return []
        if content_type == "livery":
            records = list(self._custom_liveries())
            if getattr(self, "_fh6_hidden_navigation_scope", False):
                records = [
                    record
                    for record in records
                    if not self._fh6_v132_is_livery_hidden(
                        self._content_annotation_key("livery", record)
                    )
                ]
            return records
        if content_type == "tuning":
            return list(self.result.tunings)
        return []

    def _sorted_saved_content(
        self,
        content_type: str,
    ) -> list[LiveryRecord | TuningRecord]:
        records = self._saved_content_records(content_type)
        mode = (
            self._livery_sort_mode
            if content_type == "livery"
            else self._tuning_sort_mode
        )
        descending = (
            self._livery_sort_descending
            if content_type == "livery"
            else self._tuning_sort_descending
        )

        sorted_records = sort_records(
            records,
            SortSpec(mode=mode, descending=descending),
            self._car_label,
        )
        if (
            content_type == "livery"
            and getattr(self, "_fh6_v132_initial_scan_build", False)
        ):
            return [
                record
                for record in sorted_records
                if not isinstance(record, LiveryRecord) or record.kind == "Livery"
            ]
        return sorted_records

    def _sorted_liveries(self) -> list[LiveryRecord]:
        return [
            record
            for record in self._sorted_saved_content("livery")
            if isinstance(record, LiveryRecord)
        ]

    def _sorted_tunings(self) -> list[TuningRecord]:
        return [
            record
            for record in self._sorted_saved_content("tuning")
            if isinstance(record, TuningRecord)
        ]

    @Slot(str)
    def _set_saved_content_sort_mode(
        self,
        content_type: str,
        mode: str,
    ) -> None:
        if (
            content_type not in {"livery", "tuning"}
            or mode not in {"default", "brand", "creator", "download"}
        ):
            return

        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
        # Download order is a flat chronology. Disable grouping when the mode
        # is selected, but keep the buttons available for a later user choice.
        if mode == "download":
            for button_name, pref_name in (
                (f"{content_type}_group_button", f"{content_type}_group_by_vehicle"),
                (f"{content_type}_creator_group_button", f"{content_type}_group_by_creator"),
            ):
                group_button = getattr(self, button_name)
                if group_button.isChecked():
                    group_button.blockSignals(True)
                    group_button.setChecked(False)
                    group_button.blockSignals(False)
                    self.local_preferences.set_bool(pref_name, False)

        mode_attr = (
            "_livery_sort_mode"
            if content_type == "livery"
            else "_tuning_sort_mode"
        )
        descending_attr = (
            "_livery_sort_descending"
            if content_type == "livery"
            else "_tuning_sort_descending"
        )
        previous_mode = getattr(self, mode_attr)
        previous_descending = bool(getattr(self, descending_attr))
        if mode == "download" and previous_mode != mode:
            next_descending = True
        else:
            next_descending = (
                not previous_descending if previous_mode == mode else False
            )
        setattr(self, descending_attr, next_descending)
        setattr(self, mode_attr, mode)
        self._update_sort_button_labels(content_type)

        if self.result is None:
            return

        populate = (
            self._populate_livery_table
            if content_type == "livery"
            else self._populate_tuning_table
        )
        self._view_operations.request(
            content_type,
            tr("content.sorting", noun=noun),
            populate,
        )

    def _update_sort_button_labels(self, content_type: str) -> None:
        buttons = (
            self.livery_sort_buttons
            if content_type == "livery"
            else self.tuning_sort_buttons
        )
        mode = self._livery_sort_mode if content_type == "livery" else self._tuning_sort_mode
        descending = (
            self._livery_sort_descending
            if content_type == "livery"
            else self._tuning_sort_descending
        )
        labels = {
            "default": tr("content.sort_default"),
            "brand": tr("content.sort_brand"),
            "creator": tr("content.sort_creator"),
            "download": tr("content.sort_download"),
        }
        for key, button in buttons.items():
            arrow = ("↓" if descending else "↑") if key == mode else ""
            button.setText(labels[key] + arrow)

    @Slot(str)
    def _set_livery_sort_mode(self, mode: str) -> None:
        # Compatibility wrapper used by older internal call sites.
        self._set_saved_content_sort_mode("livery", mode)

    def _car_label(self, car_id: Optional[int]) -> str:
        if car_id is None:
            return "Unknown vehicle"
        info = self.car_db.get(car_id)
        return info.label or f"Car ID {car_id}"

    def _content_annotation_key(
        self,
        content_type: str,
        record: LiveryRecord | TuningRecord,
    ) -> str:
        namespace = "tuning" if content_type == "tuning" else "livery"
        return self.annotations.instance_key_for(
            record.header.guid,
            record.container_name,
            namespace=namespace,
        )

    def _annotation_key(self, record: LiveryRecord) -> str:
        # Every physical livery container has independent UI state, even when
        # duplicate downloads share the same content GUID.
        return self._content_annotation_key("livery", record)

    def _record_for_content_key(
        self,
        content_type: str,
        key: str,
    ) -> Optional[LiveryRecord | TuningRecord]:
        if self._fh6_record_index_ready:
            return self._fh6_record_by_key.get(content_type, {}).get(key)
        for record in self._saved_content_records(content_type):
            if self._content_annotation_key(
                content_type,
                record,
            ) == key:
                return record
        return None

    def _record_for_annotation_key(
        self,
        key: str,
    ) -> Optional[LiveryRecord]:
        record = self._record_for_content_key("livery", key)
        return record if isinstance(record, LiveryRecord) else None

    def _fh6_v132_is_livery_hidden(self, key: str) -> bool:
        return is_livery_hidden(self.local_preferences, key)

    def _fh6_v132_set_livery_hidden(self, key: str, hidden: bool) -> None:
        set_livery_hidden(self.local_preferences, key, hidden)
        self._reset_game_navigation_sessions()
        self._filter_livery_views(
            self.livery_search.text(),
            preserve_scroll=True,
        )
        _sync_cached_hidden_card(self, key, hidden)

    def _fh6_v132_is_auction_applied(self, record: object) -> bool:
        return is_auction_livery_registered(self, record)

    def _reset_game_navigation_sessions(self) -> None:
        self._game_navigation_generation += 1
        self._game_navigation_pending = False
        sessions: dict[str, GameGridSession] = {}
        self._fh6_hidden_navigation_scope = True
        try:
            for content_type in ("livery", "tuning"):
                records = self._saved_content_records(content_type)
                sessions[content_type] = GameGridSession(
                    NavigationItem(
                        key=self._content_annotation_key(content_type, record),
                        car_id=record.car_id,
                        tie_breaker="|".join(
                            (
                                record.container_name,
                                record.header.guid or "",
                                record.header.name or "",
                            )
                        ),
                    )
                    for record in records
                )
        finally:
            self._fh6_hidden_navigation_scope = False
        self._game_navigation_sessions = sessions

    def _request_game_navigation(
        self,
        content_type: str,
        key: str,
    ) -> None:
        record = self._record_for_content_key(content_type, key)
        if content_type == "livery" and is_auction_livery(record):
            return
        if content_type == "livery" and self._fh6_v132_is_livery_hidden(key):
            labels = visibility_labels((get_language() or "ko").startswith("ko"))
            self._show_status(labels["hidden_move"], 3500)
            return
        if self._game_navigation_pending:
            QMessageBox.information(
                self,
                tr("navigation.pending_title"),
                tr("navigation.pending_message"),
            )
            return
        session = self._game_navigation_sessions.get(content_type)
        if session is None or record is None or not session.contains(key):
            QMessageBox.warning(
                self,
                tr("navigation.unavailable_title"),
                tr("navigation.unavailable_message"),
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("navigation.dialog_title"))
        dialog.setModal(True)
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        target_name = record.header.name or tr("detail.no_title")
        vehicle_name = self._car_label(record.car_id)

        target_panel = QFrame()
        target_panel.setObjectName("panel")
        target_layout = QVBoxLayout(target_panel)
        target_layout.setContentsMargins(12, 9, 12, 9)
        target_layout.setSpacing(2)
        vehicle_label = QLabel(vehicle_name)
        vehicle_label.setStyleSheet("font-weight: 700; font-size: 11pt;")
        title_label = QLabel(target_name)
        title_label.setObjectName("muted")
        target_layout.addWidget(vehicle_label)
        target_layout.addWidget(title_label)
        layout.addWidget(target_panel)

        description = QLabel(tr("navigation.description"))
        description.setWordWrap(True)
        layout.addWidget(description)

        delete_notice = QLabel(tr("navigation.delete_notice"))
        delete_notice.setWordWrap(True)
        delete_notice.setStyleSheet(
            "background: #fff7e8; color: #7a4b00; border: 1px solid #f0d6a6; "
            "border-radius: 8px; padding: 8px 10px;"
        )
        layout.addWidget(delete_notice)

        settings_panel = QFrame()
        settings_panel.setObjectName("panel")
        settings_layout = QGridLayout(settings_panel)
        settings_layout.setContentsMargins(12, 9, 12, 9)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(7)
        settings_title = QLabel(tr("navigation.settings_title"))
        settings_title.setStyleSheet("font-weight: 700;")
        settings_layout.addWidget(settings_title, 0, 0, 1, 2)

        settings_layout.addWidget(QLabel(tr("navigation.delay")), 1, 0)
        delay_spin = QDoubleSpinBox()
        delay_spin.setRange(0.1, 30.0)
        delay_spin.setDecimals(1)
        delay_spin.setSingleStep(0.1)
        delay_spin.setSuffix(tr("common.seconds_suffix"))
        delay_spin.setValue(
            self.settings.value("game_navigation_delay", 1.0, float)
        )
        settings_layout.addWidget(delay_spin, 1, 1)

        settings_layout.addWidget(QLabel(tr("navigation.arrow_interval")), 2, 0)
        arrow_interval_spin = QSpinBox()
        arrow_interval_spin.setRange(20, 500)
        arrow_interval_spin.setSuffix(tr("common.milliseconds_suffix"))
        arrow_interval_spin.setValue(
            self.settings.value("game_navigation_arrow_interval_ms", 70, int)
        )
        settings_layout.addWidget(arrow_interval_spin, 2, 1)

        auto_activate_box = QCheckBox(tr("navigation.auto_activate"))
        auto_activate_box.setChecked(
            self.settings.value("game_navigation_auto_activate", True, bool)
        )
        auto_activate_box.setToolTip(tr("navigation.auto_activate_tip"))
        settings_layout.addWidget(auto_activate_box, 3, 0, 1, 2)
        settings_layout.setColumnStretch(1, 1)
        layout.addWidget(settings_panel)

        choice: dict[str, str] = {"mode": ""}
        button_row = QHBoxLayout()
        delete_button = QPushButton(tr("navigation.move_delete"))
        delete_button.setObjectName("secondary")
        apply_button = QPushButton(tr("navigation.move_apply"))
        apply_button.setObjectName("primary")
        cancel_button = QPushButton(tr("common.cancel"))
        cancel_button.setObjectName("secondary")
        delete_button.clicked.connect(
            lambda: (choice.__setitem__("mode", "delete"), dialog.accept())
        )
        apply_button.clicked.connect(
            lambda: (choice.__setitem__("mode", "apply"), dialog.accept())
        )
        cancel_button.clicked.connect(dialog.reject)
        button_row.addWidget(delete_button)
        button_row.addWidget(apply_button)
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        if dialog.exec() != QDialog.DialogCode.Accepted or not choice["mode"]:
            return
        delay = delay_spin.value()
        auto_activate = auto_activate_box.isChecked()
        arrow_interval_ms = arrow_interval_spin.value()
        try:
            planned_keys = session.plan_from_first(key)
        except GameNavigationError as exc:
            QMessageBox.warning(self, tr("navigation.unavailable_title"), str(exc))
            return
        self.settings.setValue("game_navigation_delay", delay)
        self.settings.setValue("game_navigation_auto_activate", auto_activate)
        self.settings.setValue(
            "game_navigation_arrow_interval_ms",
            arrow_interval_ms,
        )
        self._game_navigation_pending = True
        generation = self._game_navigation_generation
        mode = choice["mode"]
        delay_text = tr("navigation.delay_text", value=f"{delay:g}")
        wait_message = (
            tr("navigation.wait_auto", delay=delay_text)
            if auto_activate
            else tr("navigation.wait_manual", delay=delay_text)
        )
        self._show_status(wait_message, int((delay + 8) * 1000))
        QTimer.singleShot(
            int(round(delay * 1000)),
            lambda t=content_type, k=key, keys=planned_keys, m=mode, g=generation, a=auto_activate, ar=arrow_interval_ms:
            self._execute_game_navigation(t, k, keys, m, g, a, ar),
        )

    def _execute_game_navigation(
        self,
        content_type: str,
        key: str,
        planned_keys: list[str],
        mode: str,
        generation: int,
        auto_activate: bool,
        arrow_interval_ms: int,
    ) -> None:
        self._game_navigation_pending = False
        if generation != self._game_navigation_generation:
            self._show_status(tr("navigation.cancelled_refresh"), 5000)
            return
        session = self._game_navigation_sessions.get(content_type)
        if session is None or not session.contains(key):
            self._show_status(tr("navigation.cancelled_changed"), 5000)
            return
        try:
            window_title = send_arrow_keys_to_fh6(
                planned_keys,
                interval=arrow_interval_ms / 1000.0,
                auto_activate=auto_activate,
            )
        except GameNavigationError as exc:
            QMessageBox.warning(self, tr("navigation.cancel_title"), str(exc))
            self._show_status(tr("navigation.focus_failed"), 5000)
            return

        deleted = mode == "delete"
        session.complete_move(
            key,
            deleted=deleted,
        )
        count = len(planned_keys)
        if deleted:
            message = tr("navigation.complete_deleted", count=count, window=window_title)
        else:
            message = tr("navigation.complete_applied", count=count, window=window_title)
        self._show_status(message, 8000)


    def _populate_saved_content_table(
        self,
        content_type: str,
    ) -> None:
        table = (
            self.livery_table
            if content_type == "livery"
            else self.tuning_table
        )
        table.setRowCount(0)

        for index, record in enumerate(self._sorted_saved_content(content_type)):
            self._keep_busy_responsive(index)
            key = self._content_annotation_key(
                content_type,
                record,
            )
            annotation = self.annotations.get(key)

            row = table.rowCount()
            table.insertRow(row)
            table.setRowHeight(row, 58)

            check_item = QTableWidgetItem()
            check_item.setFlags(
                (check_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
            )
            check_item.setData(Qt.ItemDataRole.UserRole, key)
            check_item.setText(tr("table.status"))
            check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 0, check_item)
            table.setCellWidget(
                row,
                0,
                self._detail_status_button_container(
                    self._make_detail_check_button(
                        key,
                        annotation.checked,
                        content_type=content_type,
                    ),
                    self._make_detail_triangle_button(
                        key,
                        annotation.triangle,
                        content_type=content_type,
                    ),
                    self._make_detail_excluded_button(
                        key,
                        annotation.excluded,
                        content_type=content_type,
                    ),
                ),
            )

            values = (
                self._car_label(record.header.car_id),
                record.header.creator or "—",
                record.header.name or "(unnamed)",
                record.header.description or "—",
            )
            for col, value in enumerate(values, 1):
                item = QTableWidgetItem(str(value))
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEditable
                )
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    key,
                )
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter
                )
                item.setToolTip(str(value))
                if col == 1 and record.header.car_id is not None:
                    item.setToolTip(
                        f"{value}\nCar ID: {record.header.car_id}"
                    )
                table.setItem(row, col, item)

            memo_item = QTableWidgetItem()
            memo_item.setFlags(
                (memo_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
            )
            memo_item.setData(Qt.ItemDataRole.UserRole, key)
            self._set_detail_memo_item(
                memo_item,
                annotation.note,
            )
            table.setItem(row, 5, memo_item)
            table.setCellWidget(
                row,
                5,
                self._detail_table_button_container(
                    self._make_detail_memo_button(
                        key,
                        annotation.note,
                        content_type=content_type,
                    )
                ),
            )

            created_item = QTableWidgetItem(
                self._created_date_only(
                    record.header.created
                )
            )
            created_item.setFlags(
                created_item.flags()
                & ~Qt.ItemFlag.ItemIsEditable
            )
            created_item.setData(
                Qt.ItemDataRole.UserRole,
                key,
            )
            created_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            )
            created_item.setToolTip(
                record.header.created or "—"
            )
            table.setItem(row, 6, created_item)

            downloaded_text = self._downloaded_datetime(record.downloaded_at)
            downloaded_item = QTableWidgetItem(downloaded_text)
            downloaded_item.setFlags(
                downloaded_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            downloaded_item.setData(Qt.ItemDataRole.UserRole, key)
            downloaded_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            downloaded_item.setToolTip(
                downloaded_text
                if record.downloaded_at is not None
                else tr("file.timestamp_unavailable")
            )
            table.setItem(row, 7, downloaded_item)

    def _populate_livery_table(self) -> None:
        self._fh6_v132_auction_build_generation = (
            getattr(self, "_fh6_v132_auction_build_generation", 0) + 1
        )
        self._populate_livery_grid()

    @Slot(QTableWidgetItem)
    def _livery_table_item_changed(
        self,
        item: QTableWidgetItem,
    ) -> None:
        return

    @Slot(int, int)
    def _livery_table_cell_double_clicked(
        self,
        row: int,
        column: int,
    ) -> None:
        return


    def _populate_livery_grid(self) -> None:
        _populate_livery_grid_reusing_cards(self)

    def _populate_tuning_grid(self) -> None:
        _populate_tuning_grid_reusing_cards(self)

    def _clear_livery_grid_layout(self) -> None:
        _responsive_clear_grid_layout(self, "livery")

    def _clear_tuning_grid_layout(self) -> None:
        _responsive_clear_grid_layout(self, "tuning")

    def _saved_content_filter_matches(
        self,
        content_type: str,
        checked: bool,
        note: str,
        triangle: bool = False,
        excluded: bool = False,
        duplicate: bool = False,
    ) -> bool:
        filter_box = (
            self.livery_check_filter
            if content_type == "livery"
            else self.tuning_check_filter
        )
        modes = filter_box.selected_modes()
        return filter_matches(
            content_type,
            modes,
            FilterState(
                checked=checked,
                note=note,
                triangle=triangle,
                excluded=excluded,
                duplicate=duplicate,
            ),
        )

    def _duplicate_livery_hashes(self) -> set[str]:
        cached = getattr(self, "_fh6_v132_duplicate_hashes", None)
        if isinstance(cached, set):
            return cached
        counts = Counter(
            record.content_sha256
            for record in self._custom_liveries()
            if record.content_sha256
        )
        return {digest for digest, count in counts.items() if count > 1}

    def _fh6_v132_schedule_auction_cards(self) -> None:
        schedule_auction_cards(self)

    def _is_duplicate_livery(self, record: LiveryRecord | None) -> bool:
        return bool(
            record
            and not is_auction_livery(record)
            and record.content_sha256
            and record.content_sha256 in self._duplicate_livery_hashes()
        )

    def _livery_filter_matches(
        self,
        checked: bool,
        note: str,
        triangle: bool = False,
        excluded: bool = False,
        duplicate: bool = False,
    ) -> bool:
        # Compatibility wrapper for the livery grid layout code.
        return self._saved_content_filter_matches(
            "livery",
            checked,
            note,
            triangle,
            excluded,
            duplicate,
        )

    def _layout_visible_grid_cards(
        self,
        content_type: str,
        cards: list[QFrame],
    ) -> None:
        layout = (
            self.livery_grid_layout
            if content_type == "livery"
            else self.tuning_grid_layout
        )
        vehicle_group_button = getattr(self, f"{content_type}_group_button")
        creator_group_button = getattr(
            self,
            f"{content_type}_creator_group_button",
        )
        group_by_vehicle = vehicle_group_button.isChecked()
        group_by_creator = creator_group_button.isChecked()

        if group_by_creator:
            group_mode = "creator"
        elif group_by_vehicle:
            group_mode = "vehicle"
        else:
            group_mode = "none"

        sections = build_grid_sections(
            cards,
            group_mode=group_mode,
            vehicle_key=lambda card: str(
                card.property("vehicleGroupKey") or "unknown"
            ),
            vehicle_label=lambda card: str(
                card.property("vehicleGroupLabel") or "Unknown vehicle"
            ),
            creator_key=lambda card: str(
                card.property("creatorGroupKey") or "unknown"
            ),
            creator_label=lambda card: str(
                card.property("creatorGroupLabel") or tr("creator.none")
            ),
        )

        if group_mode == "none":
            for index, card in enumerate(sections[0].items):
                layout.addWidget(card, index // 2, index % 2)
                card.setVisible(True)
            return

        headers: dict[str, QLabel] = (
            self._livery_group_headers
            if content_type == "livery"
            else self._tuning_group_headers
        )
        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
        row = 0
        for section in sections:
            group_key = section.key
            group_label = section.label
            group_cards = section.items
            header = headers.get(group_key)
            if header is None:
                header = QLabel()
                header.setObjectName("vehicleGroupHeader")
                header.setStyleSheet(
                    "QLabel#vehicleGroupHeader { background:#eee9ff; color:#3e2a95; "
                    "border:1px solid #d9d0ff; border-radius:8px; padding:9px 12px; "
                    "font-size:11pt; font-weight:700; }"
                )
                header.setMinimumHeight(38)
                headers[group_key] = header
            if group_by_creator:
                header.setText(
                    tr(
                        "content.creator_group_header",
                        creator=group_label,
                        noun=noun,
                        count=len(group_cards),
                    )
                )
            else:
                header.setText(
                    tr("content.group_header", vehicle=group_label, noun=noun, count=len(group_cards))
                )
            layout.addWidget(header, row, 0, 1, 2)
            header.setVisible(True)
            row += 1
            for index, card in enumerate(group_cards):
                layout.addWidget(card, row + index // 2, index % 2)
                card.setVisible(True)
            row += (len(group_cards) + 1) // 2

    def _relayout_livery_grid(self, text: str = "") -> None:
        """Pack matching cards contiguously into two columns."""
        self.livery_grid_host.setUpdatesEnabled(False)
        self._clear_livery_grid_layout()

        visible_cards: list[QFrame] = []
        duplicate_hashes = self._duplicate_livery_hashes()
        for index, card in enumerate(self._livery_grid_cards):
            haystack = str(card.property("searchText") or "")
            checked = bool(card.property("checked"))
            triangle = bool(card.property("triangle"))
            excluded = bool(card.property("excluded"))
            key = str(card.property("annotationKey") or "")
            note = self.annotations.get(key).note if key else ""
            record = self._record_for_content_key("livery", key) if key else None
            duplicate = bool(
                isinstance(record, LiveryRecord)
                and record.content_sha256
                and record.content_sha256 in duplicate_hashes
            )
            matched = search_matches(haystack, text) and self._livery_filter_matches(
                checked,
                note,
                triangle,
                excluded,
                duplicate,
            )
            if matched and not _livery_visibility_allowed(self, card):
                matched = False
            if not matched:
                self._unload_livery_card_thumbnail(card)
            else:
                visible_cards.append(card)
            _yield_busy_events(self, force=(index == 0))

        self._layout_visible_grid_cards("livery", visible_cards)
        self.livery_grid_layout.activate()
        self.livery_grid_host.setUpdatesEnabled(True)
        self.livery_grid_host.update()

        self._sync_livery_grid_card_widths()
        _schedule_grid_followup(self, "livery")

    def _relayout_tuning_grid(self, text: str = "") -> None:
        self.tuning_grid_host.setUpdatesEnabled(False)
        self._clear_tuning_grid_layout()
        visible_cards: list[QFrame] = []
        for index, card in enumerate(self._tuning_grid_cards):
            haystack = str(card.property("searchText") or "")
            checked = bool(card.property("checked"))
            triangle = bool(card.property("triangle"))
            excluded = bool(card.property("excluded"))
            key = str(card.property("annotationKey") or "")
            note = self.annotations.get(key).note if key else ""
            matched = (
                search_matches(haystack, text)
                and self._saved_content_filter_matches(
                    "tuning", checked, note, triangle, excluded
                )
            )
            if not matched:
                self._unload_livery_card_thumbnail(card)
            else:
                visible_cards.append(card)
            _yield_busy_events(self, force=(index == 0))

        self._layout_visible_grid_cards("tuning", visible_cards)
        self.tuning_grid_layout.activate()
        self.tuning_grid_host.setUpdatesEnabled(True)
        self.tuning_grid_host.update()

        self._sync_tuning_grid_card_widths()
        _schedule_grid_followup(self, "tuning")

    def _sync_livery_grid_card_widths(self) -> None:
        _optimized_sync_grid_widths(self, "livery")

    def _sync_tuning_grid_card_widths(self) -> None:
        _optimized_sync_grid_widths(self, "tuning")

    def _make_livery_card(self, record: LiveryRecord, key: str) -> QFrame:
        return self._make_saved_content_card("livery", record, key)

    def _make_tuning_card(self, record: TuningRecord, key: str) -> QFrame:
        return self._make_saved_content_card("tuning", record, key)

    def _make_saved_content_card(
        self,
        content_type: str,
        record: LiveryRecord | TuningRecord,
        key: str,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("panel")
        card.setMinimumHeight(320)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # Thumbnail + check overlay.  The checkbox lives in a small boxed overlay
        # at the upper-right instead of consuming a separate metadata row.
        image_host = QWidget()
        image_stack = QStackedLayout(image_host)
        image_stack.setContentsMargins(0, 0, 0, 0)
        image_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setMinimumHeight(210)
        image_label.setStyleSheet("background:#f1f2f6;border-radius:9px;")
        image_label.setText("Thumbnail")
        image_label.setObjectName("muted")
        image_stack.addWidget(image_label)

        overlay = QWidget()
        # APP_STYLE gives every QWidget an opaque background.  Since this widget
        # sits above the thumbnail in StackAll mode, it must be explicitly
        # transparent or it hides the vehicle image completely.
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        overlay.setStyleSheet("background: transparent;")
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(8, 8, 8, 8)
        annotation = self.annotations.get(key)
        # Icon-only check control.  The check mark always stays visible:
        # gray = unchecked, green = checked.  There is deliberately no "체크" label.
        check_box = QToolButton()
        check_box.setCheckable(True)
        check_box.setIcon(_classification_toggle_icon("check"))
        check_box.setIconSize(QSize(22, 22))
        check_box.setChecked(annotation.checked)
        check_box.setToolTip(tr("status.toggle_check"))
        item_label = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
        check_box.setAccessibleName(tr("status.accessible_check", noun=item_label))
        check_box.setFixedSize(34, 34)
        check_box.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
            "border:1px solid #dfe1e8; border-radius:17px; font-size:16px; font-weight:800; padding:0; }"
            "QToolButton:hover { border-color:#a9adb7; background:rgba(255,255,255,250); }"
            "QToolButton:checked { color:#2e9b50; border-color:#7ac58f; background:#eef9f1; }"
            "QToolButton:checked:hover { color:#238442; border-color:#58ad72; background:#e7f6eb; }"
        )
        check_box.toggled.connect(
            lambda checked, k=key, c=card, t=content_type:
            self._set_grid_checked(t, k, c, checked)
        )

        triangle_box = QToolButton()
        triangle_box.setCheckable(True)
        triangle_box.setIcon(_classification_toggle_icon("triangle"))
        triangle_box.setIconSize(QSize(22, 22))
        triangle_box.setChecked(annotation.triangle)
        triangle_box.setToolTip(tr("status.toggle_triangle"))
        triangle_box.setAccessibleName(tr("status.accessible_triangle", noun=item_label))
        triangle_box.setFixedSize(34, 34)
        triangle_box.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
            "border:1px solid #dfe1e8; border-radius:8px; font-size:17px; font-weight:800; padding:0; }"
            "QToolButton:hover { border-color:#d4a14c; background:rgba(255,250,240,250); }"
            "QToolButton:checked { color:#d98216; border-color:#e2a64f; background:#fff5e6; }"
            "QToolButton:checked:hover { color:#c36f09; border-color:#d58d2c; background:#ffeed5; }"
        )
        triangle_box.toggled.connect(
            lambda enabled, k=key, c=card, t=content_type:
            self._set_grid_triangle(t, k, c, enabled)
        )

        excluded_box = QToolButton()
        excluded_box.setCheckable(True)
        excluded_box.setIcon(_classification_toggle_icon("excluded"))
        excluded_box.setIconSize(QSize(22, 22))
        excluded_box.setChecked(annotation.excluded)
        excluded_box.setToolTip(tr("status.toggle_excluded"))
        excluded_box.setAccessibleName(tr("status.accessible_excluded", noun=item_label))
        excluded_box.setFixedSize(34, 34)
        excluded_box.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
            "border:1px solid #dfe1e8; border-radius:8px; font-size:18px; font-weight:800; padding:0; }"
            "QToolButton:hover { border-color:#df7d86; background:rgba(255,247,248,250); }"
            "QToolButton:checked { color:#c93c49; border-color:#df7d86; background:#fff0f2; }"
            "QToolButton:checked:hover { color:#ad2936; border-color:#cf5b66; background:#ffe7ea; }"
        )
        excluded_box.toggled.connect(
            lambda enabled, k=key, c=card, t=content_type:
            self._set_grid_excluded(t, k, c, enabled)
        )

        zoom_button = QToolButton()
        zoom_button.setIcon(QIcon(_classification_pixmap("search", True, 24)))
        zoom_button.setIconSize(QSize(21, 21))
        zoom_button.setToolTip(tr("preview.enlarge"))
        zoom_button.setAccessibleName(tr("preview.enlarge"))
        zoom_button.setFixedSize(34, 34)
        zoom_button.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#555a68; "
            "border:1px solid #dfe1e8; border-radius:8px; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:rgba(247,245,255,250); }"
        )
        zoom_button.clicked.connect(
            lambda _checked=False, r=record: self._show_livery_image(r)
        )

        memo_button = QToolButton()
        memo_button.setIcon(self._detail_memo_icon(bool(annotation.note.strip())))
        memo_button.setIconSize(QSize(18, 18))
        memo_button.setToolTip(
            (annotation.note.strip() + tr("memo.edit_suffix"))
            if annotation.note.strip()
            else tr("memo.none_add")
        )
        memo_button.setAccessibleName(tr("memo.accessible", noun=item_label))
        memo_button.setFixedSize(34, 34)
        memo_button.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#555a68; "
            "border:1px solid #dfe1e8; border-radius:8px; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:rgba(247,245,255,250); }"
        )
        memo_button.clicked.connect(
            lambda _checked=False, t=content_type, k=key:
            self._handle_saved_content_memo_clicked(t, k)
        )
        memo_button.clicked.connect(
            lambda _checked=False, c=card, k=key:
            QTimer.singleShot(0, lambda: _refresh_dialog_memo_button(self, c, k))
        )

        game_move_button = None
        if not (content_type == "livery" and is_auction_livery(record)):
            game_move_button = QToolButton()
            game_move_button.setIcon(QIcon(_classification_pixmap("move", True, 24)))
            game_move_button.setIconSize(QSize(23, 23))
            game_move_button.setToolTip(tr("content.game_move_tip"))
            game_move_button.setAccessibleName(tr("content.game_move_accessible", noun=item_label))
            game_move_button.setFixedSize(38, 38)
            game_move_button.setStyleSheet(
                "QToolButton { background:rgba(255,255,255,242); color:#5f39d8; "
                "border:2px solid #8c74ee; border-radius:19px; padding:0; }"
                "QToolButton:hover { color:white; border-color:#6e4bf2; background:#6e4bf2; }"
            )
            game_move_button.clicked.connect(
                lambda _checked=False, t=content_type, k=key:
                self._request_game_navigation(t, k)
            )

        if content_type == "livery":
            info_active = bool((record.header.description or "").strip())
            info_tooltip = tr("content.livery_info_tip")
        else:
            info_active = bool(
                isinstance(record, TuningRecord)
                and record.data_path is not None
                and record.data_size == 598
            )
            info_tooltip = tr("content.tuning_info_tip")
        info_button = QToolButton()
        info_kind = "livery_info" if content_type == "livery" else "tuning_info"
        info_button.setIcon(QIcon(_classification_pixmap(info_kind, info_active, 24)))
        info_button.setIconSize(QSize(22, 22))
        info_button.setToolTip(info_tooltip)
        info_button.setAccessibleName(info_tooltip)
        info_button.setFixedSize(38, 38)
        info_button.setStyleSheet(
            "QToolButton { background:"
            + ("#f2edff" if info_active else "rgba(255,255,255,242)")
            + "; border:1px solid "
            + ("#9c86f2" if info_active else "#dfe1e8")
            + "; border-radius:9px; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:#f2edff; }"
        )
        if content_type == "livery":
            info_button.clicked.connect(
                lambda _checked=False, r=record:
                self._show_livery_metadata(r)
            )
        else:
            info_button.clicked.connect(
                lambda _checked=False, r=record:
                self._show_tuning_details(r)
            )

        overlay_actions = QVBoxLayout()
        overlay_actions.setContentsMargins(0, 0, 0, 0)
        overlay_actions.setSpacing(6)
        overlay_actions.addWidget(check_box)
        overlay_actions.addWidget(triangle_box)
        overlay_actions.addWidget(excluded_box)
        overlay_actions.addWidget(zoom_button)
        overlay_actions.addWidget(memo_button)
        overlay_actions.addStretch(1)

        left_actions = QVBoxLayout()
        left_actions.setContentsMargins(0, 0, 0, 0)
        left_actions.setSpacing(6)
        if content_type == "livery" and game_move_button is not None:
            left_actions.addWidget(game_move_button, 0, Qt.AlignmentFlag.AlignTop)
        left_actions.addStretch(1)
        left_actions.addWidget(info_button, 0, Qt.AlignmentFlag.AlignBottom)

        action_columns = QHBoxLayout()
        action_columns.setContentsMargins(0, 0, 0, 0)
        action_columns.setSpacing(0)
        action_columns.addLayout(left_actions)
        action_columns.addStretch(1)
        action_columns.addLayout(overlay_actions)
        overlay_layout.addLayout(action_columns)
        image_stack.addWidget(overlay)
        image_stack.setCurrentWidget(overlay)
        outer.addWidget(image_host)

        # Borderless hierarchy: vehicle first, then title and creator metadata.
        content_name = record.header.name or "(unnamed)"
        creator_name = record.header.creator or "—"
        vehicle_name = self._car_label(record.header.car_id)
        vehicle = CopyValueLabel(tr("card.vehicle_label"), vehicle_name)
        vehicle.setStyleSheet(
            "QLabel { background:transparent; color:#171924; border:0; padding:4px 2px 1px 2px; "
            "font-size:11.5pt; font-weight:700; }"
        )
        vehicle.setFixedHeight(31)
        vehicle.setToolTip(tr("common.copy_value_detail", label=tr("card.vehicle_label"), value=vehicle_name))
        vehicle.setMinimumWidth(0)
        vehicle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        outer.addWidget(vehicle)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(7)

        title_box = CopyValueLabel(tr("card.title_label"), content_name)
        title_box.setStyleSheet(
            "QLabel { background:transparent; color:#343744; border:0; padding:2px; "
            "font-size:10pt; font-weight:600; }"
        )
        title_box.setFixedHeight(28)
        title_box.setToolTip(tr("common.copy_value_detail", label=tr("card.title_label"), value=content_name))
        title_box.setMinimumWidth(0)
        title_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        meta_row.addWidget(title_box, 3)

        creator_box = CopyValueLabel(tr("card.creator_label"), creator_name)
        creator_box.setStyleSheet(
            "QLabel { background:transparent; color:#6d7282; border:0; padding:2px; "
            "font-size:9.5pt; font-weight:500; }"
        )
        creator_box.setFixedHeight(28)
        creator_box.setToolTip(tr("common.copy_value_detail", label=tr("card.creator_label"), value=creator_name))
        creator_box.setMinimumWidth(0)
        creator_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        meta_row.addWidget(creator_box, 2)
        outer.addLayout(meta_row)

        card._fh6_image_label = image_label
        card._fh6_thumbnail_path = record.thumbnail_path
        card._fh6_thumbnail_loaded = False
        card._fh6_check_box = check_box
        card._fh6_triangle_box = triangle_box
        card._fh6_excluded_box = excluded_box
        card._fh6_memo_button = memo_button
        card._fh6_zoom_button = zoom_button
        card._fh6_game_move_button = game_move_button
        card._fh6_info_button = info_button
        card._fh6_content_type = content_type
        self._apply_pointing_cursors(card)
        _configure_card_metadata(card)
        _configure_aspect_card(card)
        if content_type == "livery":
            _install_card_hide_button(self, card, key)
            _fix_card_actions(card)
            _repair_card_actions(card, record)
        _normalize_card_actions(card)
        if content_type == "livery":
            from .release_layout import _align_left_actions_to_right_second_third

            _align_left_actions_to_right_second_third(card)
        return card

    def _livery_search_text(self, record: LiveryRecord, note: str = "") -> str:
        return self._saved_content_search_text(record, note)

    def _saved_content_search_text(
        self,
        record: LiveryRecord | TuningRecord,
        note: str = "",
    ) -> str:
        return build_search_text(record, self._car_label, note)

    def _refresh_card_search_text(self, card: QFrame, key: str) -> None:
        content_type = str(
            getattr(card, "_fh6_content_type", "livery")
        )
        record = self._record_for_content_key(content_type, key)
        if record is not None:
            card.setProperty(
                "searchText",
                self._saved_content_search_text(
                    record, self.annotations.get(key).note
                ),
            )

    def _filter_saved_content_table(
        self,
        content_type: str,
        text: str,
    ) -> None:
        table = (
            self.livery_table
            if content_type == "livery"
            else self.tuning_table
        )
        needle = text.strip().lower()

        for row in range(table.rowCount()):
            key_item = table.item(row, 0)
            key = (
                str(
                    key_item.data(Qt.ItemDataRole.UserRole)
                    or ""
                )
                if key_item
                else ""
            )
            annotation = (
                self.annotations.get(key)
                if key
                else None
            )
            checked = (
                bool(annotation.checked)
                if annotation is not None
                else False
            )
            triangle = (
                bool(annotation.triangle)
                if annotation is not None
                else False
            )
            excluded = (
                bool(annotation.excluded)
                if annotation is not None
                else False
            )
            memo = (
                annotation.note or ""
                if annotation is not None
                else ""
            )

            record = (
                self._record_for_content_key(
                    content_type,
                    key,
                )
                if key
                else None
            )
            duplicate = self._is_duplicate_livery(record) if isinstance(record, LiveryRecord) else False
            car_id_text = (
                str(record.header.car_id)
                if (
                    record is not None
                    and record.header.car_id is not None
                )
                else ""
            )

            visible_text = " ".join(
                table.item(row, col).text()
                if table.item(row, col)
                else ""
                for col in (1, 2, 3, 4, 6, 7)
            )
            hay = " ".join(
                (visible_text, car_id_text, memo)
            ).lower()

            table.setRowHidden(
                row,
                bool(
                    (needle and needle not in hay)
                    or not self._saved_content_filter_matches(
                        content_type,
                        checked,
                        memo,
                        triangle,
                        excluded,
                        duplicate,
                    )
                ),
            )
            if content_type == "livery" and not table.isRowHidden(row):
                modes = self.livery_check_filter.selected_modes()
                hidden = self._fh6_v132_is_livery_hidden(key) if key else False
                if (HIDDEN_MODE in modes and not hidden) or (
                    HIDDEN_MODE not in modes and hidden
                ):
                    table.setRowHidden(row, True)
                    continue
                if AUCTION_APPLIED_MODE in modes or AUCTION_UNAPPLIED_MODE in modes:
                    if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
                        table.setRowHidden(row, True)
                        continue
                    applied = self._fh6_v132_is_auction_applied(record)
                    if (
                        AUCTION_APPLIED_MODE in modes and not applied
                    ) or (
                        AUCTION_UNAPPLIED_MODE in modes and applied
                    ):
                        table.setRowHidden(row, True)
                if (
                    not table.isRowHidden(row)
                    and AUCTION_APPLIED_MODE not in modes
                    and AUCTION_UNAPPLIED_MODE not in modes
                    and is_unapplied_auction_livery(self, record)
                ):
                    table.setRowHidden(row, True)

    def _request_saved_content_filter(
        self,
        content_type: str,
        text: str,
    ) -> None:
        """Queue user-initiated filtering so its progress overlay can paint."""

        if self.result is None:
            self._filter_saved_content_views(
                content_type,
                text,
                preserve_scroll=True,
            )
            return
        noun = (
            tr("content.noun_livery")
            if content_type == "livery"
            else tr("content.noun_tuning")
        )
        self._view_operations.request(
            content_type,
            tr("content.filtering", noun=noun),
            lambda: self._filter_saved_content_views(
                content_type,
                text,
                preserve_scroll=True,
            ),
        )

    def _filter_saved_content_views(
        self,
        content_type: str,
        text: str,
        preserve_scroll: bool = False,
    ) -> None:
        if content_type == "livery":
            self._filter_livery_views(
                text,
                preserve_scroll=preserve_scroll,
            )
            return
        if content_type == "tuning":
            scrollbar = self.tuning_grid_scroll.verticalScrollBar()
            old_scroll = scrollbar.value()
            self._filter_saved_content_table(
                "tuning",
                text,
            )
            self._relayout_tuning_grid(text)
            if not preserve_scroll:
                self.tuning_table.scrollToTop()
                scrollbar.setValue(0)
            else:
                self._restore_grid_scroll(scrollbar, old_scroll)
                QTimer.singleShot(
                    0,
                    self._schedule_visible_tuning_thumbnails,
                )

    @staticmethod
    def _restore_grid_scroll(scrollbar: object, value: int) -> None:
        """Restore after both the immediate and deferred Qt layout passes."""
        def restore() -> None:
            scrollbar.setValue(min(value, scrollbar.maximum()))

        restore()
        QTimer.singleShot(0, restore)
        QTimer.singleShot(30, restore)

    def _refresh_after_annotation_change(
        self,
        content_type: str,
        *,
        filter_modes: set[int],
        search_sensitive: bool = False,
    ) -> None:
        """Relayout only when the changed annotation can affect visibility.

        Rebuilding a grouped grid for every button click briefly collapses the
        scroll area and causes both flicker and a jump to the first card.  In
        the normal ``All`` view the annotation only changes the clicked card,
        so no layout work is required.
        """
        filter_box = (
            self.livery_check_filter
            if content_type == "livery"
            else self.tuning_check_filter
        )
        search = (
            self.livery_search
            if content_type == "livery"
            else self.tuning_search
        )
        if filter_box.selected_modes().intersection(filter_modes) or (
            search_sensitive and bool(search.text().strip())
        ):
            self._filter_saved_content_views(
                content_type,
                search.text(),
                preserve_scroll=True,
            )

    @Slot(str)
    def _filter_livery_views(self, text: str, preserve_scroll: bool = False) -> None:
        # Checking/unchecking used to jump the grid to the top because every
        # annotation refresh reset the vertical scrollbar.  Preserve the exact
        # current position for annotation-driven refreshes; direct user searches
        # and filter changes still start at the top intentionally.
        scrollbar = self.livery_grid_scroll.verticalScrollBar()
        old_scroll = scrollbar.value()

        self._filter_saved_content_table(
            "livery",
            text,
        )
        self._relayout_livery_grid(text)

        if preserve_scroll:
            self._restore_grid_scroll(scrollbar, old_scroll)
            QTimer.singleShot(0, self._schedule_visible_livery_thumbnails)
        else:
            scrollbar.setValue(0)

    def _set_grid_checked(
        self,
        content_type: str,
        key: str,
        card: QFrame,
        checked: bool,
    ) -> None:
        self.annotations.set_checked(key, checked)
        card.setProperty("checked", checked)
        self._sync_saved_content_annotation(content_type, key)
        self._refresh_after_annotation_change(
            content_type, filter_modes={1, 10}
        )

    def _set_grid_triangle(
        self,
        content_type: str,
        key: str,
        card: QFrame,
        enabled: bool,
    ) -> None:
        self.annotations.set_triangle(key, enabled)
        card.setProperty("triangle", enabled)
        self._sync_saved_content_annotation(content_type, key)
        self._refresh_after_annotation_change(
            content_type, filter_modes={5, 10}
        )

    def _set_grid_excluded(
        self,
        content_type: str,
        key: str,
        card: QFrame,
        enabled: bool,
    ) -> None:
        self.annotations.set_excluded(key, enabled)
        card.setProperty("excluded", enabled)
        self._sync_saved_content_annotation(content_type, key)
        self._refresh_after_annotation_change(
            content_type, filter_modes={7, 10}
        )

    def _save_grid_note(self, key: str, editor: QPlainTextEdit) -> None:
        note = editor.toPlainText().strip()
        self.annotations.set_note(key, note)
        card = self._livery_card_by_key.get(key)
        if card is not None:
            self._refresh_card_search_text(card, key)
        self._sync_table_annotation(key)
        self._show_status(tr("memo.saved"), 2500)
        self._filter_livery_views(self.livery_search.text(), preserve_scroll=True)


    def _sync_saved_content_annotation(
        self,
        content_type: str,
        key: str,
    ) -> None:
        annotation = self.annotations.get(key)
        table = (
            self.livery_table
            if content_type == "livery"
            else self.tuning_table
        )

        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if (
                item is None
                or str(
                    item.data(Qt.ItemDataRole.UserRole)
                    or ""
                ) != key
            ):
                continue

            status_widget = table.cellWidget(row, 0)
            if status_widget is not None:
                for object_name, enabled in (
                    ("detailCheckButton", annotation.checked),
                    ("detailTriangleButton", annotation.triangle),
                    ("detailExcludedButton", annotation.excluded),
                ):
                    button = status_widget.findChild(QToolButton, object_name)
                    if button is not None:
                        button.blockSignals(True)
                        button.setChecked(enabled)
                        button.blockSignals(False)

            memo_item = table.item(row, 5)
            if memo_item is not None:
                self._set_detail_memo_item(
                    memo_item,
                    annotation.note,
                )
            memo_widget = table.cellWidget(row, 5)
            if memo_widget is not None:
                button = memo_widget.findChild(QToolButton)
                if button is not None:
                    note = (
                        annotation.note or ""
                    ).strip()
                    button.setIcon(
                        self._detail_memo_icon(
                            bool(note)
                        )
                    )
                    button.setToolTip(
                        (
                            note
                            + tr("memo.edit_suffix")
                        )
                        if note
                        else tr("memo.none_add")
                    )
            break
        _sync_cached_annotation_card(self, content_type, key)

    def _sync_table_annotation(
        self,
        key: str,
    ) -> None:
        self._sync_saved_content_annotation(
            "livery",
            key,
        )

    def _creator_livery_note_count(self, creator: str) -> int:
        creator_key = (creator or "").strip().casefold()
        if not creator_key:
            return 0
        return sum(
            1
            for record in self._custom_liveries()
            if (record.header.creator or "").strip().casefold() == creator_key
            and self.annotations.get(self._annotation_key(record)).note.strip()
        )

    def _apply_note_to_same_creator(self, source_key: str, source_note: str) -> None:
        source_record = self._record_for_annotation_key(source_key)
        if source_record is None:
            return
        creator = (source_record.header.creator or "").strip()
        note = (source_note or "").strip()
        if not creator:
            QMessageBox.information(self, tr("memo.creator_missing_title"), tr("memo.creator_missing_apply"))
            return
        if not note:
            QMessageBox.information(self, tr("memo.missing_title"), tr("memo.enter_first"))
            return

        creator_key = creator.casefold()
        targets = [
            record
            for record in self._custom_liveries()
            if (record.header.creator or "").strip().casefold() == creator_key
        ]
        answer = QMessageBox.question(
            self,
            tr("memo.append_confirm_title"),
            tr(
                "memo.append_confirm_message",
                creator=creator,
                targets=len(targets),
                existing=self._creator_livery_note_count(creator),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        # Keep the source editor as the authoritative text for the selected item.
        # Every other target preserves its existing memo and receives this text below it.
        self.annotations.set(source_key, note=note, save=False)
        affected = 0
        for record in targets:
            key = self._annotation_key(record)
            current = self.annotations.get(key).note
            merged = append_note(current, note)
            if merged != current:
                affected += 1
            self.annotations.set(key, note=merged, save=False)
        self.annotations.save()
        self._refresh_annotation_widgets()
        self._show_status(tr("memo.apply_status", creator=creator), 3500)
        QMessageBox.information(
            self,
            tr("memo.apply_title"),
            tr(
                "memo.apply_message",
                creator=creator,
                targets=len(targets),
                affected=affected,
            ),
        )

    def _clear_notes_for_same_creator(self, source_key: str) -> bool:
        source_record = self._record_for_annotation_key(source_key)
        if source_record is None:
            return False
        creator = (source_record.header.creator or "").strip()
        if not creator:
            QMessageBox.information(self, tr("memo.creator_missing_title"), tr("memo.creator_missing_remove"))
            return False

        creator_key = creator.casefold()
        targets = [
            record for record in self._custom_liveries()
            if (record.header.creator or "").strip().casefold() == creator_key
        ]
        with_notes = sum(
            1 for record in targets
            if self.annotations.get(self._annotation_key(record)).note.strip()
        )
        if with_notes == 0:
            QMessageBox.information(self, tr("memo.none_to_remove_title"), tr("memo.none_to_remove_message", creator=creator))
            return False

        answer = QMessageBox.question(
            self,
            tr("memo.clear_title"),
            tr("memo.clear_message", creator=creator, count=with_notes),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False

        for record in targets:
            key = self._annotation_key(record)
            self.annotations.set(key, note="", save=False)
        self.annotations.save()
        self._refresh_annotation_widgets()
        self._show_status(tr("memo.clear_status", creator=creator, count=with_notes), 3500)
        return True



    def _refresh_annotation_widgets(self) -> None:
        self.livery_table.blockSignals(True)
        try:
            for row in range(self.livery_table.rowCount()):
                item = self.livery_table.item(row, 0)
                if not item:
                    continue
                key = str(item.data(Qt.ItemDataRole.UserRole) or "")
                annotation = self.annotations.get(key)

                status_widget = self.livery_table.cellWidget(row, 0)
                if status_widget is not None:
                    for object_name, enabled in (
                        ("detailCheckButton", annotation.checked),
                        ("detailTriangleButton", annotation.triangle),
                        ("detailExcludedButton", annotation.excluded),
                    ):
                        button = status_widget.findChild(QToolButton, object_name)
                        if button is not None:
                            button.blockSignals(True)
                            button.setChecked(enabled)
                            button.blockSignals(False)

                memo = self.livery_table.item(row, 5)
                if memo is not None:
                    self._set_detail_memo_item(memo, annotation.note)
                memo_widget = self.livery_table.cellWidget(row, 5)
                if memo_widget is not None:
                    button = memo_widget.findChild(QToolButton)
                    if button is not None:
                        note = (annotation.note or "").strip()
                        button.setIcon(self._detail_memo_icon(bool(note)))
                        button.setToolTip(
                            (note + tr("memo.edit_suffix")) if note else tr("memo.none_add")
                        )
        finally:
            self.livery_table.blockSignals(False)

        for key, card in self._livery_card_by_key.items():
            annotation = self.annotations.get(key)
            checkbox = getattr(card, "_fh6_check_box", None)
            if checkbox is not None:
                checkbox.blockSignals(True)
                checkbox.setChecked(annotation.checked)
                checkbox.blockSignals(False)
            editor = getattr(card, "_fh6_memo_editor", None)
            if editor is not None:
                editor.setPlainText(annotation.note)
            card.setProperty("checked", annotation.checked)
            triangle_box = getattr(card, "_fh6_triangle_box", None)
            if triangle_box is not None:
                triangle_box.blockSignals(True)
                triangle_box.setChecked(annotation.triangle)
                triangle_box.blockSignals(False)
            card.setProperty("triangle", annotation.triangle)
            excluded_box = getattr(card, "_fh6_excluded_box", None)
            if excluded_box is not None:
                excluded_box.blockSignals(True)
                excluded_box.setChecked(annotation.excluded)
                excluded_box.blockSignals(False)
            card.setProperty("excluded", annotation.excluded)
            self._refresh_card_search_text(card, key)
        self._filter_livery_views(self.livery_search.text(), preserve_scroll=True)


    @Slot()
    def _apply_selected_table_note_to_creator(self) -> None:
        rows = self.livery_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, tr("memo.select_livery_title"), tr("memo.select_livery_message"))
            return
        row = rows[0].row()
        key_item = self.livery_table.item(row, 0)
        memo_item = self.livery_table.item(row, 5)
        if not key_item or not memo_item:
            return
        key = str(
            key_item.data(Qt.ItemDataRole.UserRole) or ""
        )
        note = self.annotations.get(key).note
        self._apply_note_to_same_creator(key, note)

    @Slot(int)
    def _on_main_page_changed(self, index: int) -> None:
        """Prime lazy thumbnails when a hidden stacked page becomes visible.

        QStackedWidget emits currentChanged before all child geometry has
        necessarily completed its final layout.  Run one immediate pass and a
        few short deferred passes; each pass is cheap because already-loaded
        cards return immediately.  This removes the previous dependency on a
        user-generated resize or scrollbar event.
        """
        if index == 1:
            self._prime_livery_grid_thumbnails()
            for delay_ms in (0, 40, 120):
                QTimer.singleShot(delay_ms, self._prime_livery_grid_thumbnails)
        elif index == 2:
            self._prime_tuning_grid_thumbnails()
            for delay_ms in (0, 40, 120):
                QTimer.singleShot(delay_ms, self._prime_tuning_grid_thumbnails)

    def _prime_livery_grid_thumbnails(self) -> None:
        if not hasattr(self, "livery_grid_scroll"):
            return
        # Ignore delayed callbacks after the user has already changed pages.
        if hasattr(self, "pages") and self.pages.currentIndex() != 1:
            return
        self.livery_grid_layout.activate()
        self.livery_grid_host.updateGeometry()
        self._sync_livery_grid_card_widths()
        self._refresh_visible_livery_thumbnails()
        self.livery_grid_scroll.viewport().update()

    def _prime_tuning_grid_thumbnails(self) -> None:
        if not hasattr(self, "tuning_grid_scroll"):
            return
        if hasattr(self, "pages") and self.pages.currentIndex() != 2:
            return
        self.tuning_grid_layout.activate()
        self.tuning_grid_host.updateGeometry()
        self._sync_tuning_grid_card_widths()
        self._refresh_visible_tuning_thumbnails()
        self.tuning_grid_scroll.viewport().update()

    def _schedule_visible_livery_thumbnails(self) -> None:
        QTimer.singleShot(0, self._refresh_visible_livery_thumbnails)

    def _schedule_visible_tuning_thumbnails(self) -> None:
        QTimer.singleShot(0, self._refresh_visible_tuning_thumbnails)

    def _refresh_visible_livery_thumbnails(self) -> None:
        if not hasattr(self, "livery_grid_scroll"):
            return
        viewport = self.livery_grid_scroll.viewport()
        visible = viewport.rect().adjusted(0, -260, 0, 260)
        for card in self._livery_grid_cards:
            if not card.isVisible():
                self._unload_livery_card_thumbnail(card)
                continue
            top_left = card.mapTo(viewport, QPoint(0, 0))
            card_rect = QRect(top_left, card.size())
            if card_rect.intersects(visible):
                self._load_livery_card_thumbnail(card)
            else:
                self._unload_livery_card_thumbnail(card)

    def _refresh_visible_tuning_thumbnails(self) -> None:
        if not hasattr(self, "tuning_grid_scroll"):
            return
        viewport = self.tuning_grid_scroll.viewport()
        visible = viewport.rect().adjusted(0, -260, 0, 260)
        for card in self._tuning_grid_cards:
            if not card.isVisible():
                self._unload_livery_card_thumbnail(card)
                continue
            top_left = card.mapTo(viewport, QPoint(0, 0))
            card_rect = QRect(top_left, card.size())
            if card_rect.intersects(visible):
                self._load_livery_card_thumbnail(card)
            else:
                self._unload_livery_card_thumbnail(card)

    def _load_livery_card_thumbnail(self, card: QFrame) -> None:
        if getattr(card, "_fh6_thumbnail_loaded", False):
            controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
            if controller is not None:
                controller.schedule()
            return
        label = getattr(card, "_fh6_image_label", None)
        controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
        path = getattr(card, "_fh6_thumbnail_path", None)
        if not isinstance(label, QLabel):
            return
        cache = getattr(self, "_fh6_thumbnail_pixmap_cache", None)
        if cache is not None and hasattr(cache, "get_or_load"):
            pixmap = cache.get_or_load(path)
        else:
            pixmap = _load_original_pixmap(path)
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setText("No thumbnail")
            label.setObjectName("muted")
            if controller is not None:
                controller.clear_source()
        else:
            label.setObjectName("muted")
            if controller is not None:
                controller.set_source(pixmap)
            else:
                label.setText("")
                label.setPixmap(pixmap)
        card._fh6_thumbnail_loaded = True

    def _unload_livery_card_thumbnail(self, card: QFrame) -> None:
        if not getattr(card, "_fh6_thumbnail_loaded", False):
            return
        controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
        if controller is not None:
            controller.clear_source()
        label = getattr(card, "_fh6_image_label", None)
        if isinstance(label, QLabel):
            label.setPixmap(QPixmap())
            label.setText("Thumbnail")
            label.setObjectName("muted")
        card._fh6_thumbnail_loaded = False

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        for content_type in ("livery", "tuning"):
            scroll = getattr(self, f"{content_type}_grid_scroll", None)
            if scroll is None or watched is not scroll.viewport():
                continue
            if event_type == QEvent.Type.Resize:
                _schedule_resize_settle(self)
                _optimized_sync_grid_widths(self, content_type)
                break
            if event_type == QEvent.Type.Show:
                _optimized_sync_grid_widths(self, content_type)
                prime = getattr(self, f"_prime_{content_type}_grid_thumbnails")
                QTimer.singleShot(0, prime)
                break
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_busy_overlay"):
            self._busy_overlay.setGeometry(self.rect())
        page_index = self.pages.currentIndex() if hasattr(self, "pages") else -1
        if page_index == 1 and hasattr(self, "livery_grid_scroll"):
            _schedule_resize_settle(self)
            _optimized_sync_grid_widths(self, "livery")
        elif page_index == 2 and hasattr(self, "tuning_grid_scroll"):
            _schedule_resize_settle(self)
            _optimized_sync_grid_widths(self, "tuning")

    def closeEvent(self, event) -> None:
        _save_window_geometry(self)
        super().closeEvent(event)

    def _populate_tuning_table(self) -> None:
        self._populate_tuning_grid()

    def _fh6_v132_reset_ui_card_cache(
        self,
        *,
        clear_pixmaps: bool = False,
    ) -> None:
        _delete_cached_cards(self, clear_pixmaps=clear_pixmaps)

    def _fh6_v132_ensure_ui_scan_generation(self) -> None:
        _ensure_scan_generation(self)

    def _current_unknown_car_ids(self) -> list[int]:
        if not self.result:
            return []
        return self.car_db.unknown_ids(summary.car_id for summary in self.result.car_summaries)

    def _refresh_db_status(self, unknown_ids: Optional[list[int]] = None) -> None:
        """Refresh the compact DB metadata shown beside the dashboard title."""
        if not hasattr(self, "db_last_update_label"):
            return

        status = self.car_db.status
        raw = (status.cache_updated_at or "").strip()

        if raw:
            # Stored value is UTC ISO-8601, e.g. 2026-08-12T14:21:04Z.
            date_text = raw[:10] if len(raw) >= 10 else raw
            self.db_last_update_label.setText(
                tr("db.last_update", date=date_text)
            )
            tooltip = tr("db.local_download_time", value=raw)
            if status.cache_source_last_modified:
                tooltip += tr("db.source_last_modified", value=status.cache_source_last_modified)
            self.db_last_update_label.setToolTip(tooltip)
        else:
            self.db_last_update_label.setText(tr("db.last_update_unavailable"))
            self.db_last_update_label.setToolTip(
                tr("db.not_updated_tip")
            )

    @Slot()
    def _open_car_db_source(self) -> None:
        QDesktopServices.openUrl(QUrl(REMOTE_SOURCE_PAGE))

    @Slot()
    def start_car_db_update(self) -> None:
        if self._db_update_thread and self._db_update_thread.isRunning():
            return
        answer = QMessageBox.question(
            self,
            tr("db.update_title"),
            tr("db.update_prompt"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.db_update_button.setEnabled(False)
        self.db_update_button.setText(tr("db.checking"))
        self._begin_busy(tr("db.updating_busy"))
        self._show_status(tr("db.downloading"))
        thread = QThread(self)
        worker = CarDatabaseUpdateWorker(self.car_db.cache_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._car_db_update_finished)
        worker.failed.connect(self._car_db_update_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._car_db_update_cleanup)
        self._db_update_thread = thread
        self._db_update_worker = worker
        thread.start()

    @Slot(object)
    def _car_db_update_finished(self, update) -> None:
        self._end_busy()
        self.car_db = CarDatabase(self.project_root / "data" / "car_names.json")
        self._refresh_db_status()
        self._show_status(tr("db.update_complete_status", count=update.count), 8000)
        QMessageBox.information(
            self,
            tr("db.update_complete_title"),
            tr("db.update_complete_message", count=update.count, path=update.cache_path),
        )
        if self.path_edit.text():
            self.start_scan(Path(self.path_edit.text()))

    @Slot(str)
    def _car_db_update_failed(self, message: str) -> None:
        self._end_busy()
        self._show_status(tr("db.update_failed"), 6000)
        QMessageBox.critical(self, tr("db.update_failed"), message)

    @Slot()
    def _car_db_update_cleanup(self) -> None:
        self._db_update_thread = None
        self._db_update_worker = None
        if hasattr(self, "db_update_button"):
            self.db_update_button.setEnabled(True)
            self.db_update_button.setText(tr("db.check_update"))

    @Slot()
    def open_car_db_override(self) -> None:
        """Spreadsheet-style Car ID -> vehicle-name editor with explicit Save."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("db.override_title"))
        dialog.resize(820, 680)
        dialog.setStyleSheet(
            APP_STYLE
            + """
            QDialog { background:#f7f8fb; }
            QTableWidget {
                background:white;
                border:1px solid #dfe1e8;
                border-radius:10px;
                gridline-color:#e8eaf0;
                selection-background-color:#eee9ff;
                selection-color:#171924;
            }
            QTableWidget::item { padding:6px 8px; }
            QHeaderView::section {
                background:#fafbfc;
                color:#5f6474;
                border:0;
                border-bottom:1px solid #dfe1e8;
                padding:8px;
                font-weight:600;
            }
            """
        )

        root = QVBoxLayout(dialog)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        table = self._table((tr("table.car_id"), tr("table.vehicle_name")))
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 120)
        table.verticalHeader().setVisible(True)
        table.verticalHeader().setDefaultSectionSize(31)
        root.addWidget(table, 1)

        # The table is the editor.  Only one explicit action remains below it.
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch(1)

        save_button = QPushButton(tr("common.save"))
        save_button.setObjectName("primary")
        save_button.setEnabled(False)
        save_button.setMinimumWidth(92)
        footer.addWidget(save_button)
        root.addLayout(footer)

        initial_overrides = self.car_db.user_overrides()
        effective = self.car_db.all_items()

        visible_ids = set(effective)
        if self.result is not None:
            visible_ids.update(
                summary.car_id for summary in self.result.car_summaries
            )

        ids = sorted(visible_ids)
        table.setRowCount(len(ids))

        for row, car_id in enumerate(ids):
            id_item = QTableWidgetItem(str(car_id))
            id_item.setData(Qt.ItemDataRole.UserRole, car_id)
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            id_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

            current_label = self.car_db.get(car_id).label
            name_item = QTableWidgetItem(current_label)
            name_item.setData(Qt.ItemDataRole.UserRole, car_id)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

            if car_id in initial_overrides:
                name_item.setBackground(QColor("#f3efff"))
                name_item.setToolTip(tr("db.override_applied_tip"))
            else:
                name_item.setToolTip(tr("db.override_edit_tip"))

            table.setItem(row, 0, id_item)
            table.setItem(row, 1, name_item)

        dirty = {"value": False}
        saved_any = {"value": False}

        def mark_dirty(item: QTableWidgetItem) -> None:
            if item.column() != 1:
                return
            dirty["value"] = True
            save_button.setEnabled(True)

        def collect_overrides() -> Optional[dict[int, str]]:
            desired: dict[int, str] = {}

            for row in range(table.rowCount()):
                id_item = table.item(row, 0)
                name_item = table.item(row, 1)
                if id_item is None or name_item is None:
                    continue

                car_id = int(id_item.data(Qt.ItemDataRole.UserRole))
                value = name_item.text().strip()

                if not value:
                    QMessageBox.warning(
                        dialog,
                        tr("db.name_check_title"),
                        tr("db.name_empty_message", car_id=car_id),
                    )
                    table.setCurrentCell(row, 1)
                    table.editItem(name_item)
                    return None

                if value != self.car_db.base_label(car_id):
                    desired[car_id] = value

            return desired

        def refresh_override_marks(
            overrides: dict[int, str],
        ) -> None:
            for row in range(table.rowCount()):
                id_item = table.item(row, 0)
                name_item = table.item(row, 1)
                if id_item is None or name_item is None:
                    continue
                car_id = int(id_item.data(Qt.ItemDataRole.UserRole))
                if car_id in overrides:
                    name_item.setBackground(QColor("#f3efff"))
                    name_item.setToolTip(tr("db.override_applied_tip"))
                else:
                    name_item.setBackground(
                        QColor(Qt.GlobalColor.transparent)
                    )
                    name_item.setToolTip(tr("db.override_edit_tip"))

        def save_overrides() -> None:
            desired = collect_overrides()
            if desired is None:
                return

            try:
                self.car_db.replace_user_overrides(desired)
            except (OSError, ValueError) as exc:
                QMessageBox.critical(
                    dialog,
                    tr("db.override_save_failed"),
                    str(exc),
                )
                return

            refresh_override_marks(desired)
            dirty["value"] = False
            saved_any["value"] = True
            save_button.setEnabled(False)
            self._show_status(
                tr("db.override_saved", count=len(desired)),
                2000,
            )

        table.itemChanged.connect(mark_dirty)
        save_button.clicked.connect(save_overrides)
        self._apply_pointing_cursors(dialog)
        dialog.exec()

        # Only saved changes are reflected in the main dashboard.
        if saved_any["value"]:
            self.car_db.reload()
            self._refresh_db_status()
            if self.path_edit.text() and Path(self.path_edit.text()).is_dir():
                self.start_scan(Path(self.path_edit.text()))


    def _dashboard_selection_search_text(self) -> str:
        if self.dashboard_content_stack.currentIndex() == 0:
            rows = self.car_table.selectionModel().selectedRows()
            if not rows:
                return ""
            item = self.car_table.item(rows[0].row(), 0)
            if item is None:
                return ""
            try:
                car_id = int(item.data(Qt.ItemDataRole.UserRole))
            except (TypeError, ValueError):
                return ""
            return self._car_label(car_id).strip()

        rows = self.creator_table.selectionModel().selectedRows()
        if not rows:
            return ""
        item = self.creator_table.item(rows[0].row(), 1)
        if item is None:
            return ""
        creator = str(
            item.data(Qt.ItemDataRole.UserRole) or item.text() or ""
        ).strip()
        if creator == tr("creator.none"):
            return ""
        return creator

    def _jump_to_dashboard_selection(self, content_type: str) -> None:
        if content_type not in {"livery", "tuning"}:
            return
        query = self._dashboard_selection_search_text()
        if not query:
            QMessageBox.information(
                self,
                tr("dashboard.instant_move_unavailable_title"),
                tr("dashboard.instant_move_unavailable_message"),
            )
            return

        page_index = 1 if content_type == "livery" else 2
        search = self.livery_search if content_type == "livery" else self.tuning_search

        self.nav_buttons[page_index].setChecked(True)
        self.pages.setCurrentIndex(page_index)
        search.blockSignals(True)
        search.setText(query)
        search.blockSignals(False)
        self._filter_saved_content_views(content_type, query)
        search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        search.selectAll()

    def _set_dashboard_content_mode(self, index: int) -> None:
        if index not in (0, 1):
            return
        self.dashboard_content_stack.setCurrentIndex(index)
        self.car_search.blockSignals(True)
        self.car_search.clear()
        self.car_search.blockSignals(False)

        if index == 0:
            self.car_search.setPlaceholderText(tr("dashboard.search_vehicle"))
            self.selected_hint.clear()
            self.selected_hint.hide()
            if self.car_table.rowCount() and not self.car_table.selectionModel().selectedRows():
                self.car_table.selectRow(0)
            self._update_selected_car()
        else:
            self.car_search.setPlaceholderText(tr("dashboard.search_creator"))
            self.selected_hint.clear()
            self.selected_hint.hide()
            if self.creator_table.rowCount() and not self.creator_table.selectionModel().selectedRows():
                self.creator_table.selectRow(0)
            self._update_selected_creator()
        self._filter_dashboard_table("")

    def _update_selected_car(self) -> None:
        if not self.result or self.dashboard_content_stack.currentIndex() != 0:
            return
        rows=self.car_table.selectionModel().selectedRows()
        if not rows: return
        item=self.car_table.item(rows[0].row(),0)
        if not item: return
        car_id=int(item.data(Qt.ItemDataRole.UserRole))
        summary=next((x for x in self.result.car_summaries if x.car_id==car_id),None)
        self.selected_title.setText(
            tr("dashboard.selected_vehicle", value=summary.label if summary else self._car_label(car_id))
        )
        self.selected_hint.clear()
        self.selected_hint.hide()
        liveries=[x for x in self.result.liveries if x.car_id==car_id and x.kind=="Livery"]
        tunings=[x for x in self.result.tunings if x.car_id==car_id]
        self._fill_selected_liveries(liveries)
        self._fill_selected_tunings(tunings)

    def _update_selected_creator(self) -> None:
        if not self.result or self.dashboard_content_stack.currentIndex() != 1:
            return
        rows = self.creator_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.creator_table.item(rows[0].row(), 1)
        if not item:
            return
        creator = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        creator_key = creator.casefold()

        def same_creator(raw_name: str) -> bool:
            display = (raw_name or "").strip() or tr("creator.none")
            return display.casefold() == creator_key

        liveries = [
            record for record in self.result.liveries
            if record.kind == "Livery" and same_creator(record.header.creator or "")
        ]
        tunings = [
            record for record in self.result.tunings
            if same_creator(record.header.creator or "")
        ]
        self.selected_title.setText(tr("dashboard.selected_creator", value=creator))
        self.selected_hint.clear()
        self.selected_hint.hide()
        self._fill_selected_liveries(liveries)
        self._fill_selected_tunings(tunings)

    def _fill_selected_liveries(self, records: list[LiveryRecord]) -> None:
        t=self.selected_liveries; t.setRowCount(0)
        for r in records:
            row=t.rowCount(); t.insertRow(row); t.setRowHeight(row,54)
            it=QTableWidgetItem(); it.setIcon(self._icon_for(r.thumbnail_path)); t.setItem(row,0,it)
            for c,v in enumerate((r.header.name or "(unnamed)",r.header.creator),1): t.setItem(row,c,QTableWidgetItem(str(v)))

    def _fill_selected_tunings(self, records: list[TuningRecord]) -> None:
        t=self.selected_tunings; t.setRowCount(0)
        for r in records:
            row=t.rowCount(); t.insertRow(row); t.setRowHeight(row,54)
            it=QTableWidgetItem(); it.setIcon(self._icon_for(r.thumbnail_path)); t.setItem(row,0,it)
            for c,v in enumerate((r.header.name or "(unnamed)",r.header.creator,self._fmt_bytes(r.data_size)),1): t.setItem(row,c,QTableWidgetItem(str(v)))

    def _apply_pointing_cursors(self, root: QWidget) -> None:
        """Use the hand cursor for controls that are intended to be clicked."""
        for button in root.findChildren(QAbstractButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    @Slot(int, int)
    def _update_livery_table_cursor(
        self,
        row: int,
        column: int,
    ) -> None:
        if column in (0, 6):
            self.livery_table.viewport().setCursor(
                Qt.CursorShape.PointingHandCursor
            )
        else:
            self.livery_table.viewport().setCursor(
                Qt.CursorShape.ArrowCursor
            )

    @staticmethod
    def _detail_view_icon() -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#555a68"))
        pen.setWidthF(1.8)
        painter.setPen(pen)
        for y in (6, 12, 18):
            painter.drawRoundedRect(3, y - 2, 4, 4, 1, 1)
            painter.drawLine(10, y, 21, y)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _grid_view_icon() -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#555a68"))
        pen.setWidthF(1.8)
        painter.setPen(pen)
        for x in (3, 13):
            for y in (3, 13):
                painter.drawRoundedRect(x, y, 8, 8, 1.5, 1.5)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _external_link_icon() -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor("#555a68"))
        pen.setWidthF(1.8)
        painter.setPen(pen)

        # Window/body
        painter.drawRoundedRect(4, 8, 12, 11, 2, 2)

        # External arrow
        painter.drawLine(11, 13, 20, 4)
        painter.drawLine(14, 4, 20, 4)
        painter.drawLine(20, 4, 20, 10)

        painter.end()
        return QIcon(pixmap)

    def _show_livery_metadata(self, record: LiveryRecord) -> None:
        key = self._content_annotation_key("livery", record)
        labels = visibility_labels((get_language() or "ko").startswith("ko"))
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("detail.livery_info_title"))
        dialog.setModal(True)
        dialog.resize(560, 360)
        dialog.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        vehicle = QLabel(self._car_label(record.header.car_id))
        vehicle.setStyleSheet("font-size:13pt;font-weight:700;")
        layout.addWidget(vehicle)
        title = QLabel(tr("detail.livery_prefix", name=record.header.name or tr("detail.no_title")))
        title.setObjectName("muted")
        layout.addWidget(title)

        hide_row = QHBoxLayout()
        hide_row.addStretch(1)
        hide_button = QToolButton()
        hide_button.setCheckable(True)
        icon = QIcon()
        icon.addPixmap(eye_slash_pixmap(False), QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap(eye_slash_pixmap(True), QIcon.Mode.Normal, QIcon.State.On)
        hide_button.setIcon(icon)
        hide_button.setIconSize(QSize(22, 22))
        hide_button.setChecked(self._fh6_v132_is_livery_hidden(key))
        hide_button.setToolTip(labels["hide_toggle"])
        hide_button.setAccessibleName(labels["hide_toggle"])
        hide_button.setFixedSize(38, 38)
        hide_button.setStyleSheet(
            "QToolButton { background:white; border:1px solid #dfe1e8; "
            "border-radius:9px; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:#f5f2ff; }"
            "QToolButton:checked { border-color:#8c74ee; background:#eee9ff; }"
        )
        hide_button.toggled.connect(
            lambda enabled, content_key=key: self._fh6_v132_set_livery_hidden(
                content_key, enabled
            )
        )
        hide_row.addWidget(hide_button)
        layout.addLayout(hide_row)

        layout.addWidget(QLabel(tr("detail.description")))
        description = QPlainTextEdit()
        description.setReadOnly(True)
        description.setPlainText(
            (record.header.description or "").strip() or tr("detail.no_description")
        )
        layout.addWidget(description, 1)
        uploaded = record.header.created or tr("common.unavailable")
        layout.addWidget(QLabel(tr("detail.uploaded", date=uploaded)))
        close_button = QPushButton(tr("common.close"))
        close_button.setObjectName("primary")
        close_button.clicked.connect(dialog.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_button)
        layout.addLayout(row)
        self._apply_pointing_cursors(dialog)
        dialog.exec()

    def _show_tuning_details(self, record: TuningRecord) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("detail.tuning_title"))
        dialog.setModal(True)
        dialog.resize(720, 720)
        dialog.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        heading = QLabel(self._car_label(record.header.car_id))
        heading.setStyleSheet("font-size:13pt;font-weight:700;")
        layout.addWidget(heading)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        lines = [
            tr("detail.basic_info"),
            tr("detail.title_line", value=record.header.name or tr("detail.no_title")),
            tr("detail.creator_line", value=record.header.creator or "—"),
            tr("detail.description_line", value=(record.header.description or "").strip() or tr("detail.no_description")),
            tr("detail.uploaded", date=record.header.created or tr("common.unavailable")),
            "",
        ]
        if record.data_path is None:
            lines.extend((tr("detail.data_file"), tr("detail.data_missing")))
        else:
            try:
                parsed = read_tune_data(record.data_path)
            except TuneDataError as exc:
                lines.extend((tr("detail.data_file"), tr("detail.read_failed", error=exc)))
            else:
                lines.extend(
                    (
                        tr("detail.data_file"),
                        tr("detail.format_version", value=parsed.format_version),
                        tr("detail.lock_state", value=tr("detail.locked") if parsed.locked else tr("detail.unlocked")),
                        tr("detail.car_ordinal", value=parsed.car_ordinal_id),
                        "",
                        tr("detail.installed_parts"),
                    )
                )
                lines.extend(
                    f"0x{offset:04X}  {label}: 0x{value:08X}"
                    for offset, label, value in parsed.parts
                )
                lines.extend(("", tr("detail.tuning_values")))
                lines.extend(
                    f"0x{offset:04X}  {label}: {value:.6g}"
                    for offset, label, value in parsed.values
                )
                if record.header.car_id is not None:
                    lines.extend(
                        (
                            "",
                            tr("detail.validation"),
                            tr("detail.header_car_id", value=record.header.car_id),
                            tr("detail.data_ordinal", value=parsed.car_ordinal_id),
                        )
                    )
        details.setPlainText("\n".join(lines))
        layout.addWidget(details, 1)
        close_button = QPushButton(tr("common.close"))
        close_button.setObjectName("primary")
        close_button.clicked.connect(dialog.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_button)
        layout.addLayout(row)
        dialog.exec()

    @staticmethod
    def _magnifier_icon() -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#555a68"))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawEllipse(4, 4, 11, 11)
        painter.drawLine(14, 14, 21, 21)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _creator_apply_icon() -> QIcon:
        """Two-person + arrow glyph for 'apply this memo to same creator'."""
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#555a68"))
        pen.setWidthF(1.7)
        painter.setPen(pen)

        # Two compact user silhouettes.
        painter.drawEllipse(2, 4, 5, 5)
        painter.drawArc(1, 10, 8, 7, 0, 180 * 16)
        painter.drawEllipse(8, 5, 5, 5)
        painter.drawArc(7, 11, 8, 7, 0, 180 * 16)

        # Arrow to the right = propagate/apply.
        painter.drawLine(14, 12, 22, 12)
        painter.drawLine(18, 8, 22, 12)
        painter.drawLine(18, 16, 22, 12)
        painter.end()
        return QIcon(pixmap)

    def _show_livery_image(
        self,
        record: LiveryRecord | TuningRecord,
    ) -> None:
        path = record.thumbnail_path
        if not path or not path.is_file():
            QMessageBox.information(
                self,
                tr("image.none_title"),
                tr("image.none_message"),
            )
            return

        try:
            image = QImage.fromData(path.read_bytes())
        except OSError as exc:
            QMessageBox.warning(self, tr("image.read_failed"), str(exc))
            return

        if image.isNull():
            QMessageBox.warning(
                self,
                tr("image.read_failed"),
                tr("image.format_failed"),
            )
            return

        dialog = QDialog(self)
        livery_name = record.header.name or "(unnamed)"
        car_name = self._car_label(record.header.car_id)
        dialog.setWindowTitle(f"{livery_name} — {car_name}")
        dialog.setModal(True)
        dialog.setStyleSheet(
            APP_STYLE
            + "QDialog { background:#f7f8fb; }"
        )

        available = self.screen().availableGeometry()
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

        self._apply_pointing_cursors(dialog)
        dialog.exec()

    @staticmethod
    def _detail_check_icon(checked: bool) -> QIcon:
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border = QColor("#d8dbe5")
        fill = QColor("#f4f5f8")
        mark = QColor("#9aa0af")

        if checked:
            border = QColor("#d9d1ff")
            fill = QColor("#f2edff")
            mark = QColor("#6e4bf2")

        painter.setPen(QPen(border, 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(2, 2, 18, 18, 6, 6)

        painter.setPen(QPen(mark, 2.0))
        painter.drawLine(7, 11, 10, 14)
        painter.drawLine(10, 14, 15, 8)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _detail_memo_icon(has_note: bool) -> QIcon:
        return QIcon(_classification_pixmap("memo", has_note, 22))

    @staticmethod
    def _created_date_only(value: str) -> str:
        raw = (value or "").strip()
        match = re.match(r"^(\\d{4}-\\d{2}-\\d{2})", raw)
        if match:
            return match.group(1)
        return raw or "—"

    @staticmethod
    def _downloaded_datetime(timestamp: float | None) -> str:
        if timestamp is None:
            return "—"
        try:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            return "—"

    def _edit_content_note_dialog(
        self,
        current_note: str,
        content_type: str,
        key: str = "",
    ) -> Optional[str]:
        dialog = QDialog(self)
        dialog.setWindowTitle(
            tr("memo.livery_title")
            if content_type == "livery"
            else tr("memo.tuning_title")
        )
        dialog.setModal(True)
        dialog.resize(620 if content_type == "livery" else 520, 360 if content_type == "livery" else 260)
        dialog.setStyleSheet(
            APP_STYLE
            + """
            QDialog { background:#f7f8fb; }
            QTextEdit {
                background:white;
                border:1px solid #dfe1e8;
                border-radius:10px;
                padding:10px;
                color:#171924;
            }
            """
        )

        root = QVBoxLayout(dialog)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        livery_record = (
            self._record_for_content_key("livery", key)
            if content_type == "livery" and key
            else None
        )
        creator = ""
        creator_count_label: Optional[QLabel] = None

        if isinstance(livery_record, LiveryRecord):
            creator = (livery_record.header.creator or "").strip()
            info_row = QHBoxLayout()
            vehicle_label = QLabel(self._car_label(livery_record.header.car_id))
            vehicle_label.setStyleSheet(
                "font-size:11.5pt; font-weight:700; color:#303341;"
            )
            creator_label = QLabel(
                tr(
                    "memo.creator_value",
                    creator=creator or tr("creator.none"),
                )
            )
            creator_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            creator_label.setStyleSheet(
                "font-weight:700; color:#5f39d8;"
            )
            info_row.addWidget(vehicle_label, 1)
            info_row.addWidget(creator_label, 0)
            root.addLayout(info_row)

            creator_count_label = QLabel()
            creator_count_label.setObjectName("muted")
            root.addWidget(creator_count_label)
        else:
            label = QLabel(tr("memo.label"))
            label.setStyleSheet("font-weight:600; color:#4f5567;")
            root.addWidget(label)

        editor = QTextEdit()
        editor.setPlaceholderText(tr("memo.label"))
        editor.setPlainText(current_note or "")
        root.addWidget(editor, 1)

        def refresh_creator_count() -> None:
            if creator_count_label is None or not creator:
                if creator_count_label is not None:
                    creator_count_label.setText(
                        tr("memo.creator_note_count", count=0)
                    )
                return
            creator_count_label.setText(
                tr(
                    "memo.creator_note_count",
                    count=self._creator_livery_note_count(creator),
                )
            )

        if isinstance(livery_record, LiveryRecord):
            refresh_creator_count()
            bulk_buttons = QHBoxLayout()

            append_btn = QPushButton(tr("memo.add_same_creator"))
            append_btn.setObjectName("secondary")
            append_btn.setStyleSheet(
                "QPushButton { background:#f1faf4; color:#287a45; border:1px solid #9ed5b0; "
                "border-radius:8px; padding:8px 10px; font-weight:650; }"
                "QPushButton:hover { background:#e8f7ed; border-color:#65b47e; }"
            )
            clear_btn = QPushButton(tr("memo.clear_same_creator"))
            clear_btn.setObjectName("secondary")
            clear_btn.setStyleSheet(
                "QPushButton { background:#fff4f8; color:#a23867; border:1px solid #e4a5c1; "
                "border-radius:8px; padding:8px 10px; font-weight:650; }"
                "QPushButton:hover { background:#ffeaf3; border-color:#cb6d98; }"
            )
            append_btn.setEnabled(bool(creator))
            clear_btn.setEnabled(bool(creator))

            def append_to_creator() -> None:
                self._apply_note_to_same_creator(
                    key,
                    editor.toPlainText(),
                )
                refresh_creator_count()

            def clear_creator_notes() -> None:
                if self._clear_notes_for_same_creator(key):
                    # The selected livery was cleared by the creator-wide action too.
                    # Keep the open editor in sync so pressing Save cannot restore it.
                    editor.clear()
                    refresh_creator_count()

            append_btn.clicked.connect(append_to_creator)
            clear_btn.clicked.connect(clear_creator_notes)
            bulk_buttons.addWidget(append_btn)
            bulk_buttons.addWidget(clear_btn)
            root.addLayout(bulk_buttons)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        cancel_btn = QPushButton(tr("common.cancel"))
        cancel_btn.setObjectName("secondary")
        save_btn = QPushButton(tr("common.save"))
        save_btn.setObjectName("primary")

        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        root.addLayout(buttons)

        cancel_btn.clicked.connect(dialog.reject)
        save_btn.clicked.connect(dialog.accept)

        self._apply_pointing_cursors(dialog)
        editor.setFocus()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return editor.toPlainText().strip()
        return None

    def _edit_livery_note_dialog(
        self,
        current_note: str,
    ) -> Optional[str]:
        return self._edit_content_note_dialog(
            current_note,
            "livery",
        )


    def _detail_table_button_container(self, button: QWidget) -> QWidget:
        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(button)
        return container

    def _detail_status_button_container(
        self,
        check_button: QToolButton,
        triangle_button: QToolButton,
        excluded_button: QToolButton,
    ) -> QWidget:
        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        container.setStyleSheet("background:transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(check_button)
        layout.addWidget(triangle_button)
        layout.addWidget(excluded_button)
        return container

    def _make_detail_check_button(
        self,
        key: str,
        checked: bool,
        content_type: str = "livery",
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("detailCheckButton")
        button.setCheckable(True)
        button.setIcon(_classification_toggle_icon("check"))
        button.setIconSize(QSize(22, 22))
        button.setChecked(bool(checked))
        button.setToolTip(tr("status.toggle_check"))
        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
        button.setAccessibleName(tr("status.accessible_check", noun=noun))
        button.setFixedSize(34, 34)
        button.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
            "border:1px solid #dfe1e8; border-radius:17px; font-size:16px; font-weight:800; padding:0; }"
            "QToolButton:hover { border-color:#a9adb7; background:rgba(255,255,255,250); }"
            "QToolButton:checked { color:#2e9b50; border-color:#7ac58f; background:#eef9f1; }"
            "QToolButton:checked:hover { color:#238442; border-color:#58ad72; background:#e7f6eb; }"
        )
        button.clicked.connect(
            lambda _=False, kind=content_type, k=key, b=button:
            self._handle_saved_content_check_clicked(
                kind,
                k,
                b.isChecked(),
            )
        )
        return button

    def _make_detail_triangle_button(
        self,
        key: str,
        enabled: bool,
        content_type: str = "livery",
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("detailTriangleButton")
        button.setCheckable(True)
        button.setIcon(_classification_toggle_icon("triangle"))
        button.setIconSize(QSize(22, 22))
        button.setChecked(bool(enabled))
        button.setToolTip(tr("status.toggle_triangle"))
        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
        button.setAccessibleName(tr("status.accessible_triangle", noun=noun))
        button.setFixedSize(34, 34)
        button.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
            "border:1px solid #dfe1e8; border-radius:8px; font-size:17px; font-weight:800; padding:0; }"
            "QToolButton:hover { border-color:#d4a14c; background:rgba(255,250,240,250); }"
            "QToolButton:checked { color:#d98216; border-color:#e2a64f; background:#fff5e6; }"
            "QToolButton:checked:hover { color:#c36f09; border-color:#d58d2c; background:#ffeed5; }"
        )
        button.clicked.connect(
            lambda _=False, kind=content_type, k=key, b=button:
            self._handle_saved_content_triangle_clicked(
                kind,
                k,
                b.isChecked(),
            )
        )
        return button

    def _make_detail_memo_button(
        self,
        key: str,
        note: str,
        content_type: str = "livery",
    ) -> QToolButton:
        note = (note or "").strip()
        button = QToolButton()
        button.setIcon(self._detail_memo_icon(bool(note)))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(
            (note + tr("memo.edit_suffix")) if note else tr("memo.none_add")
        )
        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
        button.setAccessibleName(tr("memo.accessible", noun=noun))
        button.setFixedSize(34, 34)
        button.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#555a68; "
            "border:1px solid #dfe1e8; border-radius:8px; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:rgba(247,245,255,250); }"
        )
        button.clicked.connect(
            lambda _=False, kind=content_type, k=key:
            self._handle_saved_content_memo_clicked(
                kind,
                k,
            )
        )
        return button

    def _make_detail_excluded_button(
        self,
        key: str,
        enabled: bool,
        content_type: str = "livery",
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("detailExcludedButton")
        button.setCheckable(True)
        button.setIcon(_classification_toggle_icon("excluded"))
        button.setIconSize(QSize(22, 22))
        button.setChecked(bool(enabled))
        button.setToolTip(tr("status.toggle_excluded"))
        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
        button.setAccessibleName(tr("status.accessible_excluded", noun=noun))
        button.setFixedSize(34, 34)
        button.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
            "border:1px solid #dfe1e8; border-radius:8px; font-size:18px; font-weight:800; padding:0; }"
            "QToolButton:hover { border-color:#df7d86; background:rgba(255,247,248,250); }"
            "QToolButton:checked { color:#c93c49; border-color:#df7d86; background:#fff0f2; }"
            "QToolButton:checked:hover { color:#ad2936; border-color:#cf5b66; background:#ffe7ea; }"
        )
        button.clicked.connect(
            lambda _=False, kind=content_type, k=key, b=button:
            self._handle_saved_content_excluded_clicked(kind, k, b.isChecked())
        )
        return button

    def _handle_saved_content_check_clicked(
        self,
        content_type: str,
        key: str,
        checked: bool,
    ) -> None:
        self.annotations.set_checked(key, checked)
        self._sync_saved_content_annotation(
            content_type,
            key,
        )

        cards = (
            self._livery_card_by_key
            if content_type == "livery"
            else self._tuning_card_by_key
        )
        card = cards.get(key)
        if card is not None:
            checkbox = getattr(card, "_fh6_check_box", None)
            if checkbox is not None:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
            card.setProperty("checked", checked)

        self._refresh_after_annotation_change(
            content_type, filter_modes={1, 10}
        )

    def _handle_saved_content_triangle_clicked(
        self,
        content_type: str,
        key: str,
        enabled: bool,
    ) -> None:
        self.annotations.set_triangle(key, enabled)
        self._sync_saved_content_annotation(content_type, key)

        cards = (
            self._livery_card_by_key
            if content_type == "livery"
            else self._tuning_card_by_key
        )
        card = cards.get(key)
        if card is not None:
            triangle_box = getattr(card, "_fh6_triangle_box", None)
            if triangle_box is not None:
                triangle_box.blockSignals(True)
                triangle_box.setChecked(enabled)
                triangle_box.blockSignals(False)
            card.setProperty("triangle", enabled)

        self._refresh_after_annotation_change(
            content_type, filter_modes={5, 10}
        )

    def _handle_saved_content_excluded_clicked(
        self,
        content_type: str,
        key: str,
        enabled: bool,
    ) -> None:
        self.annotations.set_excluded(key, enabled)
        self._sync_saved_content_annotation(content_type, key)
        cards = self._livery_card_by_key if content_type == "livery" else self._tuning_card_by_key
        card = cards.get(key)
        if card is not None:
            excluded_box = getattr(card, "_fh6_excluded_box", None)
            if excluded_box is not None:
                excluded_box.blockSignals(True)
                excluded_box.setChecked(enabled)
                excluded_box.blockSignals(False)
            card.setProperty("excluded", enabled)
        self._refresh_after_annotation_change(
            content_type, filter_modes={7, 10}
        )

    def _handle_saved_content_memo_clicked(
        self,
        content_type: str,
        key: str,
    ) -> None:
        current = self.annotations.get(key).note
        note = self._edit_content_note_dialog(
            current,
            content_type,
            key,
        )
        if note is None:
            return

        self.annotations.set_note(key, note)
        self._sync_saved_content_annotation(
            content_type,
            key,
        )

        cards = (
            self._livery_card_by_key
            if content_type == "livery"
            else self._tuning_card_by_key
        )
        card = cards.get(key)
        if card is not None:
            self._refresh_card_search_text(card, key)
            memo_button = getattr(card, "_fh6_memo_button", None)
            if memo_button is not None:
                clean_note = (note or "").strip()
                memo_button.setIcon(self._detail_memo_icon(bool(clean_note)))
                memo_button.setToolTip(
                    (clean_note + tr("memo.edit_suffix"))
                    if clean_note
                    else tr("memo.none_add")
                )

        self._show_status(
            tr("memo.saved"),
            1800,
        )
        self._refresh_after_annotation_change(
            content_type,
            filter_modes={3, 4},
            search_sensitive=True,
        )

    def _handle_detail_check_clicked(
        self,
        key: str,
        checked: bool,
    ) -> None:
        self._handle_saved_content_check_clicked(
            "livery",
            key,
            checked,
        )

    def _handle_detail_memo_clicked(
        self,
        key: str,
    ) -> None:
        self._handle_saved_content_memo_clicked(
            "livery",
            key,
        )

    def _set_detail_check_item(
        self,
        item: QTableWidgetItem,
        checked: bool,
    ) -> None:
        item.setText("")
        item.setData(Qt.ItemDataRole.UserRole + 1, bool(checked))
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        item.setToolTip(tr("status.checked") if checked else tr("status.unchecked"))

    def _set_detail_memo_item(
        self,
        item: QTableWidgetItem,
        note: str,
    ) -> None:
        note = (note or "").strip()
        item.setText("")
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        item.setData(Qt.ItemDataRole.UserRole + 1, note)
        if note:
            item.setToolTip(note + tr("memo.edit_suffix"))
        else:
            item.setToolTip(tr("memo.none_add"))


    def _icon_for(self, path: Optional[Path]) -> QIcon:
        # Small table icons are owned by their table items. Do not keep a second
        # application-wide image cache across rescans.
        if not path or not path.is_file():
            return QIcon()
        try:
            image = QImage.fromData(path.read_bytes())
            if image.isNull():
                return QIcon()
            pix = QPixmap.fromImage(image).scaled(
                76, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            return QIcon(pix)
        except OSError:
            return QIcon()

    def _pixmap_for(self, path: Optional[Path], size: QSize) -> Optional[QPixmap]:
        if not path or not path.is_file():
            return None
        try:
            image = QImage.fromData(path.read_bytes())
            if image.isNull():
                return None
            return QPixmap.fromImage(image).scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except OSError:
            return None

    def _filter_dashboard_table(self, text: str) -> None:
        if self.dashboard_content_stack.currentIndex() == 0:
            self._filter_table(self.car_table, text, (0, 1))
        else:
            self._filter_table(self.creator_table, text, (1,))

    def _filter_car_table(self, text: str) -> None:
        # Compatibility alias for older internal call sites.
        self._filter_table(self.car_table, text, (0, 1))

    @staticmethod
    def _filter_table(table: QTableWidget, text: str, columns: tuple[int,...]) -> None:
        needle=text.strip().lower()
        for row in range(table.rowCount()):
            hay=" ".join((table.item(row,c).text() if table.item(row,c) else "") for c in columns).lower()
            table.setRowHidden(row,bool(needle and needle not in hay))

    @staticmethod
    def _fmt_bytes(size: int) -> str:
        if size < 1024: return f"{size} B"
        if size < 1024*1024: return f"{size/1024:.1f} KiB"
        return f"{size/(1024*1024):.2f} MiB"
