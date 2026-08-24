from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QSizePolicy

from . import v1_3_ui_patch as v13_ui
from . import v1_3_1_patch as v131_ui
from .v1_3_2_global_ui_patch import _AspectFitThumbnailController


# Keep the existing dense card view: a snapped half-width 1920x1080 window must
# still show at least two cards per row. Wider windows may grow to any number of
# columns; there is intentionally no hard maximum.
CARD_TARGET_WIDTH = 400
CARD_MIN_WIDTH = 340
GRID_MIN_COLUMNS = 2

# Action controls remain inside the thumbnail overlay. The largest left control
# is 38 px and the right controls are 34 px, with 8 px overlay margins. Reserving
# 48 px on each side keeps the full-aspect vehicle image away from both stacks.
THUMBNAIL_SIDE_SAFE_PX = 48


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


def apply_v1_3_2_card_width_overlay_patch(MainWindow) -> None:
    """Keep overlay actions and solve vehicle overlap through image geometry.

    Side rails are intentionally not used. Existing overlay controls stay in the
    thumbnail. The grid keeps at least two columns, has no upper column cap, and
    the native-aspect image is rendered slightly smaller and centered inside a
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

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        card.setMinimumWidth(CARD_MIN_WIDTH)
        policy = card.sizePolicy()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, policy.verticalPolicy())
        return card

    MainWindow._make_saved_content_card = patched_make_card

    # The global aspect controller already uses KeepAspectRatio. Reduce only the
    # effective render width; QLabel alignment remains centered, creating equal
    # safe space beneath the left/right overlay controls without cropping.
    if not getattr(_AspectFitThumbnailController, "_fh6_overlay_safe_width_patched", False):
        original_host_width = _AspectFitThumbnailController._host_width

        def safe_host_width(controller) -> int:
            return _safe_thumbnail_render_width(original_host_width(controller))

        _AspectFitThumbnailController._host_width = safe_host_width
        _AspectFitThumbnailController._fh6_overlay_safe_width_patched = True

    MainWindow._fh6_v132_card_width_overlay_patched = True
