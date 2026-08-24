from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import LiveryRecord, TuningRecord
from .ui import _classification_pixmap
from .v1_3_2_visibility_patch import _eye_slash_pixmap


ACTION_BUTTON_SIZE = 20
ACTION_ICON_SIZE = 14
ACTION_RAIL_WIDTH = 28
ACTION_ROW_COUNT = 5

ACTIVE_GLYPH = "#6e4bf2"
INACTIVE_GLYPH = "#9ba5b3"
ACTIVE_BORDER = "#8c74ee"
INACTIVE_BORDER = "#d4d7e0"
ACTIVE_BACKGROUND = "#eee9ff"
INACTIVE_BACKGROUND = "#ffffff"


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


def _monochrome_pixmap(source: QPixmap, color: str, size: int = ACTION_ICON_SIZE) -> QPixmap:
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    if source.isNull():
        return result

    fitted = source.scaled(
        QSize(size, size),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(result)
    x = (size - fitted.width()) // 2
    y = (size - fitted.height()) // 2
    painter.drawPixmap(x, y, fitted)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QColor(color))
    painter.end()
    return result


def _glyph_pixmap(kind: str, active: bool) -> QPixmap:
    if kind == "hide":
        source = _eye_slash_pixmap(active, 24)
    else:
        source = _classification_pixmap(kind, active, 24)
    return _monochrome_pixmap(
        source,
        ACTIVE_GLYPH if active else INACTIVE_GLYPH,
    )


def _button_style(active: bool) -> str:
    background = ACTIVE_BACKGROUND if active else INACTIVE_BACKGROUND
    border = ACTIVE_BORDER if active else INACTIVE_BORDER
    return (
        "QToolButton {"
        f"background:{background}; border:1px solid {border}; "
        "border-radius:5px; padding:0; margin:0;"
        "}"
        "QToolButton:hover {"
        "background:#e8e1ff; border-color:#6e4bf2;"
        "}"
        "QToolButton:pressed {"
        "background:#ddd3ff; border-color:#5f39d8;"
        "}"
        "QToolButton:disabled {"
        "background:#f4f5f8; border-color:#e1e3e9;"
        "}"
    )


def _apply_button_visual(button: QToolButton, kind: str, active: bool) -> None:
    try:
        button.setFixedSize(ACTION_BUTTON_SIZE, ACTION_BUTTON_SIZE)
        button.setIconSize(QSize(ACTION_ICON_SIZE, ACTION_ICON_SIZE))
        button.setIcon(QIcon(_glyph_pixmap(kind, active)))
        button.setStyleSheet(_button_style(active))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("fh6RailKind", kind)
        button.setProperty("fh6RailActive", bool(active))
    except RuntimeError:
        return


def _detach_legacy_aligners(card: QWidget, overlay: QWidget | None) -> None:
    if overlay is None:
        return
    for attr in ("_fh6_card_action_aligner", "_fh6_hide_aligner"):
        aligner = getattr(card, attr, None)
        if aligner is None:
            continue
        try:
            overlay.removeEventFilter(aligner)
        except RuntimeError:
            pass
        try:
            aligner.deleteLater()
        except RuntimeError:
            pass
        setattr(card, attr, None)


def _make_rail(parent: QWidget) -> tuple[QWidget, QGridLayout]:
    rail = QWidget(parent)
    rail.setObjectName("fh6CardActionRail")
    rail.setFixedWidth(ACTION_RAIL_WIDTH)
    rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    rail.setStyleSheet("background:transparent;")

    layout = QGridLayout(rail)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setHorizontalSpacing(0)
    layout.setVerticalSpacing(0)
    layout.setColumnStretch(0, 1)
    for row in range(ACTION_ROW_COUNT):
        layout.setRowStretch(row, 1)
    return rail, layout


def _safe_button(card: QWidget, attr: str) -> QToolButton | None:
    button = getattr(card, attr, None)
    if not isinstance(button, QToolButton):
        return None
    try:
        button.objectName()
    except RuntimeError:
        return None
    return button


def _place_button(
    button: QToolButton | None,
    layout: QGridLayout,
    row: int,
    *,
    visible: bool = True,
) -> None:
    if button is None:
        return
    button.setProperty("fh6RailIncluded", bool(visible))
    if not visible:
        button.hide()
        return
    button.setParent(layout.parentWidget())
    layout.addWidget(button, row, 0, Qt.AlignmentFlag.AlignCenter)
    button.show()


def _info_active(content_type: str, record: Any) -> bool:
    if content_type == "livery":
        return bool((getattr(record.header, "description", "") or "").strip())
    return bool(
        isinstance(record, TuningRecord)
        and record.data_path is not None
        and record.data_size == 598
    )


def _sync_card_rail_states(self: Any, card: QWidget) -> None:
    key = str(getattr(card, "_fh6_rail_annotation_key", "") or "")
    annotation = self.annotations.get(key) if key else None

    entries = (
        ("_fh6_check_box", "check", lambda b: b.isChecked()),
        ("_fh6_triangle_box", "triangle", lambda b: b.isChecked()),
        ("_fh6_excluded_box", "excluded", lambda b: b.isChecked()),
        ("_fh6_hide_button", "hide", lambda b: b.isChecked()),
        ("_fh6_zoom_button", "search", lambda _b: True),
        (
            "_fh6_game_move_button",
            "move",
            lambda b: b.isEnabled() and bool(b.property("fh6RailIncluded")),
        ),
        (
            "_fh6_memo_button",
            "memo",
            lambda _b: bool(annotation is not None and (annotation.note or "").strip()),
        ),
        (
            "_fh6_info_button",
            str(getattr(card, "_fh6_rail_info_kind", "info")),
            lambda _b: bool(getattr(card, "_fh6_rail_info_active", False)),
        ),
    )

    for attr, kind, resolver in entries:
        button = _safe_button(card, attr)
        if button is None:
            continue
        try:
            active = bool(resolver(button))
        except RuntimeError:
            continue
        _apply_button_visual(button, kind, active)


def _connect_live_state_updates(self: Any, card: QWidget) -> None:
    for attr, kind in (
        ("_fh6_check_box", "check"),
        ("_fh6_triangle_box", "triangle"),
        ("_fh6_excluded_box", "excluded"),
        ("_fh6_hide_button", "hide"),
    ):
        button = _safe_button(card, attr)
        if button is None:
            continue
        button.toggled.connect(
            lambda enabled, b=button, k=kind: _apply_button_visual(b, k, bool(enabled))
        )

    memo = _safe_button(card, "_fh6_memo_button")
    if memo is not None:
        memo.clicked.connect(
            lambda _checked=False, c=card: QTimer.singleShot(
                0,
                lambda: _sync_card_rail_states(self, c),
            )
        )


def _configure_card_action_rails(
    self: Any,
    card: QWidget,
    content_type: str,
    record: LiveryRecord | TuningRecord,
    key: str,
) -> None:
    if getattr(card, "_fh6_card_action_rails", None) is not None:
        return

    image_label = getattr(card, "_fh6_image_label", None)
    if not isinstance(image_label, QLabel):
        return
    image_host = image_label.parentWidget()
    if image_host is None:
        return

    outer = card.layout()
    if not isinstance(outer, QVBoxLayout):
        return
    image_index = outer.indexOf(image_host)
    if image_index < 0:
        return

    stack = image_host.layout()
    overlay = None
    if isinstance(stack, QStackedLayout):
        current = stack.currentWidget()
        if isinstance(current, QWidget) and current is not image_label:
            overlay = current

    _detach_legacy_aligners(card, overlay)

    buttons = [
        _safe_button(card, attr)
        for attr in (
            "_fh6_game_move_button",
            "_fh6_hide_button",
            "_fh6_info_button",
            "_fh6_check_box",
            "_fh6_triangle_box",
            "_fh6_excluded_box",
            "_fh6_zoom_button",
            "_fh6_memo_button",
        )
    ]
    if overlay is not None:
        for button in buttons:
            if button is not None:
                _remove_widget_from_layout(overlay.layout(), button)
        overlay.hide()

    outer.removeWidget(image_host)

    shell = QWidget(card)
    shell.setObjectName("fh6CardMediaShell")
    shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    shell.setStyleSheet(
        "QWidget#fh6CardMediaShell { background:#f1f2f6; border-radius:9px; }"
    )
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(4)

    left_rail, left_layout = _make_rail(shell)
    right_rail, right_layout = _make_rail(shell)

    image_host.setParent(shell)
    image_host.setMinimumWidth(1)
    image_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    image_label.setStyleSheet("background:transparent;border:0;")

    shell_layout.addWidget(left_rail)
    shell_layout.addWidget(image_host, 1)
    shell_layout.addWidget(right_rail)
    outer.insertWidget(image_index, shell)

    move = _safe_button(card, "_fh6_game_move_button")
    hide = _safe_button(card, "_fh6_hide_button")
    info = _safe_button(card, "_fh6_info_button")
    check = _safe_button(card, "_fh6_check_box")
    triangle = _safe_button(card, "_fh6_triangle_box")
    excluded = _safe_button(card, "_fh6_excluded_box")
    zoom = _safe_button(card, "_fh6_zoom_button")
    memo = _safe_button(card, "_fh6_memo_button")

    show_move = bool(
        content_type == "livery"
        and isinstance(record, LiveryRecord)
        and record.kind != "SoulBoundLivery"
        and move is not None
        and move.isEnabled()
    )

    # Five shared vertical rows make the left/right controls line up exactly:
    #   0 move/check, 1 blank/triangle, 2 blank/excluded, 3 hide/zoom, 4 info/memo.
    _place_button(move, left_layout, 0, visible=show_move)
    _place_button(hide, left_layout, 3, visible=content_type == "livery")
    _place_button(info, left_layout, 4)

    _place_button(check, right_layout, 0)
    _place_button(triangle, right_layout, 1)
    _place_button(excluded, right_layout, 2)
    _place_button(zoom, right_layout, 3)
    _place_button(memo, right_layout, 4)

    card._fh6_card_action_rails = (left_rail, right_rail)
    card._fh6_media_shell = shell
    card._fh6_rail_annotation_key = key
    card._fh6_rail_info_kind = "livery_info" if content_type == "livery" else "tuning_info"
    card._fh6_rail_info_active = _info_active(content_type, record)

    _sync_card_rail_states(self, card)
    _connect_live_state_updates(self, card)

    controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
    if controller is not None:
        controller.schedule()
        QTimer.singleShot(0, controller.schedule)


def _sync_all_card_rails(self: Any) -> None:
    seen: set[int] = set()
    for cards in (
        getattr(self, "_livery_grid_cards", []),
        getattr(self, "_tuning_grid_cards", []),
    ):
        for card in cards:
            marker = id(card)
            if marker in seen:
                continue
            seen.add(marker)
            _sync_card_rail_states(self, card)


def apply_v1_3_2_card_rail_patch(MainWindow) -> None:
    """Move card actions outside thumbnails and normalize their visual system.

    The thumbnail keeps its native aspect in the center column. All saved-content
    action controls live in fixed 28 px side rails, so no vehicle pixels can be
    covered by controls. Buttons use one 20x20 rounded-square geometry and one
    purple/gray active/inactive color system.
    """
    if getattr(MainWindow, "_fh6_v132_card_rail_patched", False):
        return

    original_make_card = MainWindow._make_saved_content_card
    original_refresh_annotations = getattr(MainWindow, "_refresh_annotation_widgets", None)

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        _configure_card_action_rails(self, card, content_type, record, key)
        return card

    MainWindow._make_saved_content_card = patched_make_card

    if callable(original_refresh_annotations):
        def patched_refresh_annotations(self) -> None:
            original_refresh_annotations(self)
            _sync_all_card_rails(self)

        MainWindow._refresh_annotation_widgets = patched_refresh_annotations

    MainWindow._fh6_v132_sync_card_rail_states = _sync_card_rail_states
    MainWindow._fh6_v132_sync_all_card_rails = _sync_all_card_rails
    MainWindow._fh6_v132_card_rail_patched = True
