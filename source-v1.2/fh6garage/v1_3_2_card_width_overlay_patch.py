from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QToolButton, QWidget

from . import v1_3_ui_patch as v13_ui
from . import v1_3_1_patch as v131_ui
from .models import LiveryRecord, TuningRecord
from .ui import _classification_pixmap
from .v1_3_2_global_ui_patch import _AspectFitThumbnailController
from .v1_3_2_visibility_patch import _eye_slash_pixmap


# Keep the existing dense card view: a snapped half-width 1920x1080 window must
# still show at least two cards per row. Wider windows may grow to any number of
# columns; there is intentionally no hard maximum.
CARD_TARGET_WIDTH = 400
CARD_MIN_WIDTH = 340
GRID_MIN_COLUMNS = 2

# Action controls remain inside the thumbnail overlay. Reserve a symmetric safe
# zone so the full-aspect vehicle image is rendered slightly smaller and centered
# instead of running beneath either action stack.
THUMBNAIL_SIDE_SAFE_PX = 48

# The rail layout is gone, but the previously requested visual normalization is
# retained for every action button while it stays in the original overlay.
ACTION_BUTTON_SIZE = 20
ACTION_ICON_SIZE = 14
ACTIVE_GLYPH = "#6e4bf2"
INACTIVE_GLYPH = "#9ba5b3"
ACTIVE_BORDER = "#8c74ee"
INACTIVE_BORDER = "#d4d7e0"
ACTIVE_BACKGROUND = "#eee9ff"
INACTIVE_BACKGROUND = "#ffffff"


def _columns_for_inner_width(inner_width: int) -> int:
    inner = max(1, int(inner_width))
    return max(GRID_MIN_COLUMNS, int(inner // CARD_TARGET_WIDTH))


def _grid_column_count(self: Any, content_type: str) -> int:
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    if scroll is None or layout is None:
        return GRID_MIN_COLUMNS

    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return GRID_MIN_COLUMNS

    margins = layout.contentsMargins()
    inner_width = max(
        1,
        viewport.width() - margins.left() - margins.right() - 4,
    )
    return _columns_for_inner_width(inner_width)


def _apply_grid_card_widths(
    self: Any,
    content_type: str,
    columns: int,
    *,
    force: bool = False,
) -> None:
    """Width sync with a two-column floor and no upper column limit."""
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    host = getattr(self, f"{content_type}_grid_host", None)
    cards = getattr(self, f"_{content_type}_grid_cards", None)
    if scroll is None or layout is None or host is None or cards is None:
        return

    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return

    columns = max(GRID_MIN_COLUMNS, int(columns))
    margins = layout.contentsMargins()
    gap = max(0, layout.horizontalSpacing())
    available = (
        viewport.width()
        - margins.left()
        - margins.right()
        - gap * (columns - 1)
        - 4
    )
    card_width = max(CARD_MIN_WIDTH, available // columns)

    last_attr = f"_fh6_v131_{content_type}_card_width"
    last_width = getattr(self, last_attr, None)
    if (
        not force
        and isinstance(last_width, int)
        and abs(card_width - last_width) < v131_ui.CARD_WIDTH_UPDATE_STEP
    ):
        return

    active_attr = f"_fh6_{content_type}_grid_columns"
    previous_columns = int(getattr(self, active_attr, columns) or columns)
    for column in range(max(previous_columns, columns)):
        stretch = 1 if column < columns else 0
        if layout.columnStretch(column) != stretch:
            layout.setColumnStretch(column, stretch)

    for card in cards:
        if card.minimumWidth() != card_width or card.maximumWidth() != card_width:
            card.setFixedWidth(card_width)

    setattr(self, last_attr, card_width)
    host.setMinimumWidth(0)
    host.updateGeometry()


def _safe_thumbnail_render_width(raw_width: int) -> int:
    return max(1, int(raw_width) - THUMBNAIL_SIDE_SAFE_PX * 2)


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


def _safe_button(card: QWidget, attr: str) -> QToolButton | None:
    button = getattr(card, attr, None)
    if not isinstance(button, QToolButton):
        return None
    try:
        button.objectName()
    except RuntimeError:
        return None
    return button


def _apply_button_visual(button: QToolButton, kind: str, active: bool) -> None:
    try:
        button.setFixedSize(ACTION_BUTTON_SIZE, ACTION_BUTTON_SIZE)
        button.setIconSize(QSize(ACTION_ICON_SIZE, ACTION_ICON_SIZE))
        button.setIcon(QIcon(_glyph_pixmap(kind, active)))
        button.setStyleSheet(_button_style(active))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("fh6OverlayKind", kind)
        button.setProperty("fh6OverlayActive", bool(active))
    except RuntimeError:
        return


def _info_active(content_type: str, record: Any) -> bool:
    if content_type == "livery":
        return bool((getattr(record.header, "description", "") or "").strip())
    return bool(
        isinstance(record, TuningRecord)
        and record.data_path is not None
        and record.data_size == 598
    )


def _sync_overlay_button_states(self: Any, card: QWidget) -> None:
    key = str(getattr(card, "_fh6_overlay_annotation_key", "") or "")
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
            lambda b: b.isEnabled() and bool(getattr(card, "_fh6_overlay_move_active", False)),
        ),
        (
            "_fh6_memo_button",
            "memo",
            lambda _b: bool(annotation is not None and (annotation.note or "").strip()),
        ),
        (
            "_fh6_info_button",
            str(getattr(card, "_fh6_overlay_info_kind", "info")),
            lambda _b: bool(getattr(card, "_fh6_overlay_info_active", False)),
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


def _connect_overlay_state_updates(self: Any, card: QWidget) -> None:
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
                lambda: _sync_overlay_button_states(self, c),
            )
        )


def _configure_overlay_buttons(
    self: Any,
    card: QWidget,
    content_type: str,
    record: LiveryRecord | TuningRecord,
    key: str,
) -> None:
    card._fh6_overlay_annotation_key = key
    card._fh6_overlay_info_kind = "livery_info" if content_type == "livery" else "tuning_info"
    card._fh6_overlay_info_active = _info_active(content_type, record)
    card._fh6_overlay_move_active = bool(
        content_type == "livery"
        and isinstance(record, LiveryRecord)
        and record.kind != "SoulBoundLivery"
    )
    _sync_overlay_button_states(self, card)
    _connect_overlay_state_updates(self, card)


def _sync_all_overlay_buttons(self: Any) -> None:
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
            _sync_overlay_button_states(self, card)


def apply_v1_3_2_card_width_overlay_patch(MainWindow) -> None:
    """Keep overlay actions and solve vehicle overlap through image geometry.

    Side rails are intentionally not used. Existing action controls stay inside
    the thumbnail, normalized to 20x20 rounded squares with one purple/gray state
    system. The grid keeps at least two columns, has no upper column cap, and the
    native-aspect image is rendered slightly smaller and centered inside a
    left/right safe zone so the controls no longer cover vehicle pixels.
    """
    if getattr(MainWindow, "_fh6_v132_card_width_overlay_patched", False):
        return

    # v1.3 generalized layout resolves this helper at runtime.
    v13_ui._grid_column_count = _grid_column_count
    MainWindow._fh6_grid_column_count = _grid_column_count

    # v1.3.1 resize/reflow helpers resolve this module-global function at
    # runtime. Preserve their debounce/reflow path and only replace width math.
    v131_ui._apply_grid_card_widths = _apply_grid_card_widths

    original_make_card = MainWindow._make_saved_content_card
    original_refresh_annotations = getattr(MainWindow, "_refresh_annotation_widgets", None)

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        card.setMinimumWidth(CARD_MIN_WIDTH)
        policy = card.sizePolicy()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, policy.verticalPolicy())
        _configure_overlay_buttons(self, card, content_type, record, key)
        return card

    MainWindow._make_saved_content_card = patched_make_card

    if callable(original_refresh_annotations):
        def patched_refresh_annotations(self) -> None:
            original_refresh_annotations(self)
            _sync_all_overlay_buttons(self)

        MainWindow._refresh_annotation_widgets = patched_refresh_annotations

    # The global aspect controller already uses KeepAspectRatio. Reduce only the
    # effective render width; QLabel alignment remains centered, creating equal
    # safe space beneath the left/right overlay controls without cropping.
    if not getattr(_AspectFitThumbnailController, "_fh6_overlay_safe_width_patched", False):
        original_host_width = _AspectFitThumbnailController._host_width

        def safe_host_width(controller) -> int:
            return _safe_thumbnail_render_width(original_host_width(controller))

        _AspectFitThumbnailController._host_width = safe_host_width
        _AspectFitThumbnailController._fh6_overlay_safe_width_patched = True

    MainWindow._fh6_v132_sync_overlay_button_states = _sync_overlay_button_states
    MainWindow._fh6_v132_sync_all_overlay_buttons = _sync_all_overlay_buttons
    MainWindow._fh6_v132_card_width_overlay_patched = True
