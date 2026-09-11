from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidgetAction,
)

from .i18n import get_language, tr
from .models import LiveryRecord
from .ui import APP_STYLE, MultiStatusFilterButton


_HIDDEN_MODE = 11
_AUCTION_APPLIED_MODE = 12
_AUCTION_UNAPPLIED_MODE = 13
_HIDDEN_PREFIX = "hidden_livery_v1_3_2:"


def _t(key: str) -> str:
    ko = (get_language() or "ko").lower().startswith("ko")
    table = {
        "hidden": ("숨김", "Hidden"),
        "hidden_tip": ("숨긴 리버리만 표시", "Show hidden liveries only"),
        "hide_toggle": ("이 리버리 숨기기", "Hide this livery"),
        "hidden_move": ("숨김 리버리는 이동 대상에서 제외됩니다.", "Hidden liveries are excluded from game movement."),
        "auction_applied": ("적용 경매장 리버리", "Applied auction livery"),
        "auction_applied_tip": (
            "현재 CacheThumbnails에 실제 대응 WebP가 존재하는 SoulBound 리버리",
            "SoulBound liveries with a currently resolvable WebP in CacheThumbnails",
        ),
        "auction_unapplied": ("미적용 경매장 리버리", "Unapplied auction livery"),
        "auction_unapplied_tip": (
            "현재 CacheThumbnails에 실제 대응 WebP가 없는 SoulBound 리버리",
            "SoulBound liveries without a currently resolvable WebP in CacheThumbnails",
        ),
    }
    value = table[key]
    return value[0] if ko else value[1]


def _eye_slash_pixmap(active: bool, size: int = 22) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#6e4bf2" if active else "#8d93a2")
    pen = QPen(color, 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.drawArc(QRect(3, 6, size - 6, size - 10), 15 * 16, 150 * 16)
    painter.drawArc(QRect(3, 6, size - 6, size - 10), 195 * 16, 150 * 16)
    painter.drawEllipse(QRect(size // 2 - 3, size // 2 - 3, 6, 6))
    painter.drawLine(4, 4, size - 4, size - 4)
    painter.end()
    return pixmap


def _cache_state_pixmap(applied: bool, size: int = 22) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#2e9b50" if applied else "#9aa0aa")
    pen = QPen(color, 1.8)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRect(3, 4, size - 6, size - 8), 3, 3)
    painter.drawLine(6, size - 7, 10, size - 11)
    painter.drawLine(10, size - 11, 13, size - 8)
    painter.drawLine(13, size - 8, size - 6, 7)
    if not applied:
        painter.drawLine(4, 4, size - 4, size - 4)
    painter.end()
    return pixmap


def _install_filter_row(
    button: MultiStatusFilterButton,
    mode: int,
    label: str,
    tooltip: str,
    icon: QIcon,
) -> None:
    menu = button.menu()
    if menu is None or mode in button._actions:
        return
    row = QPushButton(label)
    row.setCheckable(True)
    row.setIcon(icon)
    row.setIconSize(QSize(22, 22))
    row.setToolTip(tooltip)
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
        lambda checked=False, m=mode, owner=button: owner._row_toggled(m, checked)
    )
    action = QWidgetAction(menu)
    action.setDefaultWidget(row)
    menu.addAction(action)
    button._actions[mode] = row


def apply_v1_3_2_visibility_patches(MainWindow) -> None:
    """Add cache-based auction state filters and persistent livery hiding.

    Operational auction-state rule:
      - applied: SoulBoundLivery whose current thumbnail_path resolves to a real
        WebP in the active CacheThumbnails directory.
      - unapplied: SoulBoundLivery without such a currently resolvable WebP.

    This is intentionally a cache-state rule, not a claim that ProfileData was
    decoded. Hidden liveries remain in counts and storage but are omitted from
    normal list views and all game-navigation sessions.
    """
    if getattr(MainWindow, "_fh6_v132_visibility_patched", False):
        return

    original_filter_init = MultiStatusFilterButton.__init__
    original_row_toggled = MultiStatusFilterButton._row_toggled
    original_filter_saved_content_table = MainWindow._filter_saved_content_table
    original_reset_game_navigation_sessions = MainWindow._reset_game_navigation_sessions
    original_saved_content_records = MainWindow._saved_content_records
    original_request_game_navigation = MainWindow._request_game_navigation

    def filter_init(self, include_duplicate: bool, parent=None) -> None:
        original_filter_init(self, include_duplicate, parent)
        if not include_duplicate:
            return
        menu = self.menu()
        if menu is not None:
            menu.addSeparator()
        _install_filter_row(
            self,
            _HIDDEN_MODE,
            _t("hidden"),
            _t("hidden_tip"),
            QIcon(_eye_slash_pixmap(True)),
        )
        _install_filter_row(
            self,
            _AUCTION_APPLIED_MODE,
            _t("auction_applied"),
            _t("auction_applied_tip"),
            QIcon(_cache_state_pixmap(True)),
        )
        _install_filter_row(
            self,
            _AUCTION_UNAPPLIED_MODE,
            _t("auction_unapplied"),
            _t("auction_unapplied_tip"),
            QIcon(_cache_state_pixmap(False)),
        )

    def row_toggled(self, mode: int, checked: bool) -> None:
        if checked and mode in {_AUCTION_APPLIED_MODE, _AUCTION_UNAPPLIED_MODE}:
            other_mode = (
                _AUCTION_UNAPPLIED_MODE
                if mode == _AUCTION_APPLIED_MODE
                else _AUCTION_APPLIED_MODE
            )
            other = self._actions.get(other_mode)
            if other is not None and other.isChecked():
                other.blockSignals(True)
                other.setChecked(False)
                other.blockSignals(False)
        original_row_toggled(self, mode, checked)

    MultiStatusFilterButton.__init__ = filter_init
    MultiStatusFilterButton._row_toggled = row_toggled

    def hidden_pref_key(self, key: str) -> str:
        return f"{_HIDDEN_PREFIX}{key}"

    def is_hidden(self, key: str) -> bool:
        return self.local_preferences.get_bool(hidden_pref_key(self, key), False)

    def set_hidden(self, key: str, hidden: bool) -> None:
        self.local_preferences.set_bool(hidden_pref_key(self, key), bool(hidden))
        self._reset_game_navigation_sessions()
        self._filter_livery_views(
            self.livery_search.text(),
            preserve_scroll=True,
        )

    def is_auction_applied(record: Any) -> bool:
        if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
            return False
        path = record.thumbnail_path
        try:
            return bool(path is not None and path.is_file())
        except OSError:
            return False

    def filter_saved_content_table(self, content_type: str, text: str) -> None:
        original_filter_saved_content_table(self, content_type, text)
        if content_type != "livery":
            return
        modes = self.livery_check_filter.selected_modes()
        hidden_only = _HIDDEN_MODE in modes
        applied_filter = _AUCTION_APPLIED_MODE in modes
        unapplied_filter = _AUCTION_UNAPPLIED_MODE in modes

        table = self.livery_table
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            key_item = table.item(row, 0)
            key = str(key_item.data(Qt.ItemDataRole.UserRole) or "") if key_item else ""
            hidden = is_hidden(self, key) if key else False
            if hidden_only:
                if not hidden:
                    table.setRowHidden(row, True)
                    continue
            elif hidden:
                table.setRowHidden(row, True)
                continue

            if applied_filter or unapplied_filter:
                record = self._record_for_content_key("livery", key) if key else None
                if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
                    table.setRowHidden(row, True)
                    continue
                applied = is_auction_applied(record)
                if applied_filter and not applied:
                    table.setRowHidden(row, True)
                elif unapplied_filter and applied:
                    table.setRowHidden(row, True)

    def saved_content_records(self, content_type: str):
        records = original_saved_content_records(self, content_type)
        if content_type != "livery" or not getattr(
            self, "_fh6_hidden_navigation_scope", False
        ):
            return records
        return [
            record
            for record in records
            if not is_hidden(
                self,
                self._content_annotation_key("livery", record),
            )
        ]

    def reset_game_navigation_sessions(self) -> None:
        self._fh6_hidden_navigation_scope = True
        try:
            original_reset_game_navigation_sessions(self)
        finally:
            self._fh6_hidden_navigation_scope = False

    def request_game_navigation(self, content_type: str, key: str) -> None:
        if content_type == "livery" and is_hidden(self, key):
            self._show_status(_t("hidden_move"), 3500)
            return
        original_request_game_navigation(self, content_type, key)

    def show_livery_metadata(self, record: LiveryRecord) -> None:
        key = self._content_annotation_key("livery", record)
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("detail.livery_info_title"))
        dialog.setModal(True)
        dialog.resize(560, 390)
        dialog.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        vehicle = QLabel(self._car_label(record.header.car_id))
        vehicle.setStyleSheet("font-size:13pt;font-weight:700;")
        layout.addWidget(vehicle)
        title = QLabel(
            tr(
                "detail.livery_prefix",
                name=record.header.name or tr("detail.no_title"),
            )
        )
        title.setObjectName("muted")
        layout.addWidget(title)

        hide_row = QHBoxLayout()
        hide_row.setContentsMargins(0, 0, 0, 0)
        hide_row.addStretch(1)
        hide_button = QToolButton()
        hide_button.setCheckable(True)
        from .card_icons import toggle_icon as card_toggle_icon

        icon = card_toggle_icon("visible", "hidden", size=22)
        hide_button.setIcon(icon)
        hide_button.setIconSize(QSize(22, 22))
        hide_button.setChecked(is_hidden(self, key))
        hide_button.setToolTip(_t("hide_toggle"))
        hide_button.setAccessibleName(_t("hide_toggle"))
        hide_button.setFixedSize(38, 38)
        hide_button.setStyleSheet(
            "QToolButton { background:white; border:1px solid #dfe1e8; border-radius:9px; padding:0; }"
            "QToolButton:hover { border-color:#8c74ee; background:#f5f2ff; }"
            "QToolButton:checked { border-color:#8c74ee; background:#eee9ff; }"
        )
        hide_button.toggled.connect(
            lambda enabled, k=key: set_hidden(self, k, enabled)
        )
        hide_row.addWidget(hide_button)
        layout.addLayout(hide_row)

        layout.addWidget(QLabel(tr("detail.description")))
        description = QPlainTextEdit()
        description.setReadOnly(True)
        description.setPlainText(
            (record.header.description or "").strip()
            or tr("detail.no_description")
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

    MainWindow._filter_saved_content_table = filter_saved_content_table
    MainWindow._saved_content_records = saved_content_records
    MainWindow._reset_game_navigation_sessions = reset_game_navigation_sessions
    MainWindow._request_game_navigation = request_game_navigation
    MainWindow._show_livery_metadata = show_livery_metadata
    MainWindow._fh6_v132_is_livery_hidden = is_hidden
    MainWindow._fh6_v132_set_livery_hidden = set_hidden
    MainWindow._fh6_v132_is_auction_applied = staticmethod(is_auction_applied)
    MainWindow._fh6_v132_visibility_patched = True
