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
from .card_action_alignment import configure_livery_card_actions
from .card_state_sync import (
    _sync_cached_annotation_card,
    _sync_cached_hidden_card,
)
from .card_visuals import _fix_busy_overlay, _normalize_card_actions
from .car_db import CarDatabase, CarDatabaseError, REMOTE_SOURCE_PAGE
from .car_db_override_dialog import open_car_db_override_dialog
from .creator_aliases import CreatorAliasStore
from .creator_alias_view import aggregate_creator_alias_stats, sort_by_creator_alias
from .content_note_dialog import edit_content_note_dialog
from .content_detail_dialogs import show_livery_metadata, show_tuning_details
from .dashboard_page_builder import build_dashboard_page
from .game_navigation import (
    GameGridSession,
    NavigationItem,
)
from .game_navigation_controller import (
    execute_game_navigation,
    request_game_navigation,
)
from .i18n import SUPPORTED_LANGUAGES, get_language, tr
from .image_preview_dialog import show_livery_image
from .models import LiveryRecord, ScanResult, TuningRecord
from .livery_visibility import (
    AUCTION_APPLIED_MODE,
    AUCTION_UNAPPLIED_MODE,
    HIDDEN_MODE,
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
from .saved_content_card_metadata import append_card_metadata
from .saved_content_card_actions import build_card_actions
from .saved_content_controls import build_saved_content_controls
from .saved_content_presenter import (
    FilterState,
    build_search_text,
    filter_matches,
    search_matches,
)
from .saved_content_layout import _dynamic_layout_visible_grid_cards, grid_column_count
from .saved_content_view import (
    SortSpec,
    sort_records,
    vehicle_brand_sort_key,
)
from .thumbnail_display import _configure_aspect_card, _load_original_pixmap
from .ui_responsiveness import (
    _livery_visibility_allowed,
    _responsive_clear_grid_layout,
    _schedule_grid_followup,
    _yield_busy_events,
)
from .ui_cleanup import (
    _align_path_rows,
    _configure_livery_source_switch,
    _install_card_hide_button,
    _normalize_path_rows,
)
from .ui_followup import IMAGE_MIN_HEIGHT, configure_language_controls, persist_language_preference, restart_application, set_always_on_top
from .view_operations import ViewOperationCoordinator
from .auction_ui_features import (
    _add_auction_badge,
    _auto_detect_cache,
    _choose_cache_folder,
    _current_cache_path,
    _display_liveries,
    _install_cache_row,
    _install_source_controls,
    _restore_cache_path,
    _set_source_enabled,
)
from .window_responsiveness import (
    _ensure_resize_timer,
    _finalize_resize,
    _lightweight_reflow,
    _optimized_sync_grid_widths,
    _restore_window_geometry,
    _save_window_geometry,
    _schedule_resize_settle,
)
from .creator_alias_views import (
    creator_display,
    decorate_creator_copy_label,
    initialize_creator_alias_ui,
    normalize_card_alias_properties,
    open_alias_dialog,
    refresh_alias_views,
)
from .creator_change_views import (
    initialize_change_view_ui,
    open_change_dialog,
    update_change_banner,
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
        self.creator_aliases = CreatorAliasStore()
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

        self.setWindowTitle("FH6 Assistant v1.3.2")
        self.resize(1460, 900)
        # Allow a narrower compact layout while preventing the two-row toolbar
        # and card metadata from being vertically clipped.
        self.setMinimumSize(960, 680)
        QApplication.instance().setStyleSheet(APP_STYLE)
        self._build_ui()
        configure_language_controls(self)
        _install_cache_row(self)
        _restore_cache_path(self)
        initialize_creator_alias_ui(self)
        initialize_change_view_ui(self)
        _normalize_path_rows(self)
        _align_path_rows(self)
        _configure_livery_source_switch(self)
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

    def _fh6_v132_choose_cache_folder(self) -> None:
        _choose_cache_folder(self)

    def _fh6_v132_auto_detect_cache(self, *, silent: bool = False, rescan: bool = True) -> bool:
        return _auto_detect_cache(self, silent=silent, rescan=rescan)

    def _fh6_v132_set_source_enabled(self, source: str, enabled: bool) -> None:
        _set_source_enabled(self, source, enabled)

    def _fh6_v132_current_cache_path(self) -> Path | None:
        return _current_cache_path(self)

    def _fh6_v132_display_liveries(self) -> list[LiveryRecord]:
        return _display_liveries(self)
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
        persist_language_preference(self, index)

    def _restart_for_language_change(self) -> None:
        restart_application(self)

    @Slot(bool)
    def _set_always_on_top(self, enabled: bool, *, persist: bool = True) -> None:
        """Apply the topmost state with a non-flashing Windows fast path."""
        set_always_on_top(self, enabled, persist=persist)

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
        version = QLabel("v1.3.2\nLIVERY & TUNING")
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
        return build_dashboard_page(self, SummaryCard, DashboardSortBar)

    def _livery_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._page_header(tr("content.livery_page"), ""))

        (
            controls,
            self.livery_search,
            self.livery_check_filter,
            self.livery_sort_group,
            self.livery_sort_buttons,
        ) = self._build_saved_content_controls("livery")
        layout.addLayout(controls)

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
        return build_saved_content_controls(
            self,
            content_type,
            filter_button_factory=MultiStatusFilterButton,
            install_source_controls=_install_source_controls,
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
        update_change_banner(self)

    def _populate_all_content(self) -> None:
        _ensure_scan_generation(self)
        assert self.result is not None
        r = self.result
        meta = r.metadata
        self.card_cars.value.setText(str(meta.reported_car_count) if meta.reported_car_count is not None else "—")
        custom = sum(1 for x in r.liveries if x.kind == "Livery")
        self.card_livery.value.setText(str(custom))
        self.card_auction.value.setText(
            str(sum(1 for record in r.liveries if record.kind == "SoulBoundLivery"))
        )
        self.card_tuning.value.setText(str(len(r.tunings)))
        self._populate_car_table()
        self._populate_creator_table()
        self._begin_busy(tr("content.rebuilding_livery"))
        try:
            self._populate_livery_view()
        finally:
            self._end_busy()
        self._populate_tuning_view()
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
        return aggregate_creator_alias_stats(
            self.result,
            self.creator_aliases,
            tr("creator.none"),
        )

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

        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item is None:
                continue
            canonical = str(item.data(Qt.ItemDataRole.UserRole) or item.text() or "").strip()
            if not canonical or canonical == tr("creator.none"):
                continue
            item.setText(self.creator_aliases.display_name(canonical))
            item.setToolTip(" / ".join(self.creator_aliases.search_names(canonical)))

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
            records = list(self._fh6_v132_display_liveries())
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

        if mode == "creator":
            return sort_by_creator_alias(
                records,
                self.creator_aliases,
                self._vehicle_brand_sort_key,
                descending=descending,
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
            self._populate_livery_view
            if content_type == "livery"
            else self._populate_tuning_view
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
        request_game_navigation(self, content_type, key)

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
        execute_game_navigation(
            self,
            content_type,
            key,
            planned_keys,
            mode,
            generation,
            auto_activate,
            arrow_interval_ms,
        )

    def _populate_livery_view(self) -> None:
        self._fh6_v132_auction_build_generation = (
            getattr(self, "_fh6_v132_auction_build_generation", 0) + 1
        )
        self._populate_livery_grid()

    @Slot(QTableWidgetItem)
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
        _dynamic_layout_visible_grid_cards(self, content_type, cards)

    def _fh6_grid_column_count(self, content_type: str) -> int:
        return grid_column_count(self, content_type)

    def _relayout_livery_grid(self, text: str = "") -> None:
        """Pack matching cards contiguously into two columns."""
        for card in self._livery_grid_cards:
            normalize_card_alias_properties(self, "livery", card)
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
        for card in self._tuning_grid_cards:
            normalize_card_alias_properties(self, "tuning", card)
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
        image_label.setMinimumHeight(IMAGE_MIN_HEIGHT)
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
        actions = build_card_actions(
            self,
            card,
            overlay_layout,
            content_type,
            record,
            key,
            annotation,
            _classification_toggle_icon,
            _classification_pixmap,
        )
        image_stack.addWidget(overlay)
        image_stack.setCurrentWidget(overlay)
        outer.addWidget(image_host)

        append_card_metadata(self, outer, record, CopyValueLabel)

        card._fh6_image_label = image_label
        card._fh6_thumbnail_path = record.thumbnail_path
        card._fh6_thumbnail_loaded = False
        card._fh6_check_box = actions.check
        card._fh6_triangle_box = actions.triangle
        card._fh6_excluded_box = actions.excluded
        card._fh6_memo_button = actions.memo
        card._fh6_zoom_button = actions.zoom
        card._fh6_game_move_button = actions.game_move
        card._fh6_info_button = actions.info
        card._fh6_content_type = content_type
        self._apply_pointing_cursors(card)
        _configure_card_metadata(card)
        _configure_aspect_card(card)
        if content_type == "livery":
            _install_card_hide_button(self, card, key)
            configure_livery_card_actions(card, record)
            if record.kind == "SoulBoundLivery":
                card.setProperty("liverySource", "auction")
                _add_auction_badge(card)
            else:
                card.setProperty("liverySource", "my_designs")
        decorate_creator_copy_label(self, card, record.header.creator or "")
        _normalize_card_actions(card)
        return card

    def _livery_search_text(self, record: LiveryRecord, note: str = "") -> str:
        base = self._saved_content_search_text(record, note)
        source = (
            tr("content.source_auction")
            if record.kind == "SoulBoundLivery"
            else tr("content.source_my_designs")
        )
        return f"{base} {source}".lower()

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
            self._relayout_tuning_grid(text)
            if not preserve_scroll:
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

    def _populate_tuning_view(self) -> None:
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
        open_car_db_override_dialog(self, APP_STYLE)

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
        creator_key = "" if creator == tr("creator.none") else creator.casefold()

        def same_creator(raw_name: str) -> bool:
            raw = (raw_name or "").strip()
            if not raw:
                return not creator_key
            return self.creator_aliases.canonical_name(raw).casefold() == creator_key

        liveries = [
            record for record in self.result.liveries
            if record.kind == "Livery" and same_creator(record.header.creator or "")
        ]
        tunings = [
            record for record in self.result.tunings
            if same_creator(record.header.creator or "")
        ]
        display = (
            tr("creator.none")
            if not creator_key
            else self.creator_aliases.display_name(creator)
        )
        self.selected_title.setText(tr("dashboard.selected_creator", value=display))
        self.selected_hint.clear()
        self.selected_hint.hide()
        self._fill_selected_liveries(liveries)
        self._fill_selected_tunings(tunings)

    def _fill_selected_liveries(self, records: list[LiveryRecord]) -> None:
        t=self.selected_liveries; t.setRowCount(0)
        for r in records:
            row=t.rowCount(); t.insertRow(row); t.setRowHeight(row,54)
            it=QTableWidgetItem(); it.setIcon(self._icon_for(r.thumbnail_path)); t.setItem(row,0,it)
            for c,v in enumerate((r.header.name or "(unnamed)",creator_display(self, r.header.creator or "")),1): t.setItem(row,c,QTableWidgetItem(str(v)))

    def _fill_selected_tunings(self, records: list[TuningRecord]) -> None:
        t=self.selected_tunings; t.setRowCount(0)
        for r in records:
            row=t.rowCount(); t.insertRow(row); t.setRowHeight(row,54)
            it=QTableWidgetItem(); it.setIcon(self._icon_for(r.thumbnail_path)); t.setItem(row,0,it)
            for c,v in enumerate((r.header.name or "(unnamed)",creator_display(self, r.header.creator or ""),self._fmt_bytes(r.data_size)),1): t.setItem(row,c,QTableWidgetItem(str(v)))

    def _apply_pointing_cursors(self, root: QWidget) -> None:
        """Use the hand cursor for controls that are intended to be clicked."""
        for button in root.findChildren(QAbstractButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    @Slot(int, int)
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
        show_livery_metadata(self, record, app_style=APP_STYLE)

    def _show_tuning_details(self, record: TuningRecord) -> None:
        show_tuning_details(self, record, app_style=APP_STYLE)

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
        show_livery_image(self, record, app_style=APP_STYLE)

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
        return edit_content_note_dialog(
            self,
            current_note,
            content_type,
            key,
            app_style=APP_STYLE,
        )

    def _edit_livery_note_dialog(
        self,
        current_note: str,
    ) -> Optional[str]:
        return self._edit_content_note_dialog(
            current_note,
            "livery",
        )


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
            return
        needle = text.strip().casefold()
        for row in range(self.creator_table.rowCount()):
            item = self.creator_table.item(row, 1)
            if item is None:
                self.creator_table.setRowHidden(row, bool(needle))
                continue
            canonical = str(item.data(Qt.ItemDataRole.UserRole) or item.text() or "").strip()
            if not canonical or canonical == tr("creator.none"):
                haystack = item.text().casefold()
            else:
                haystack = " ".join(
                    [
                        self.creator_aliases.display_name(canonical),
                        *self.creator_aliases.search_names(canonical),
                    ]
                ).casefold()
            self.creator_table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _fh6_open_creator_alias_manager(self) -> None:
        open_alias_dialog(self)

    def _fh6_open_refresh_diff_view(self) -> None:
        open_change_dialog(self)

    def _fh6_refresh_alias_views(self) -> None:
        refresh_alias_views(self)

    def _fh6_update_refresh_diff_banner(self) -> None:
        update_change_banner(self)

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
