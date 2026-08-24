from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QSizePolicy

from . import v1_3_ui_patch as v13_ui
from . import v1_3_1_patch as v131_ui
from .v1_3_2_global_ui_patch import _AspectFitThumbnailController


# Keep cards wide enough that overlay actions no longer crowd the vehicle image.
# At a 1920x1080 desktop with the app snapped to one half (~960 px), the saved
# content viewport is expected to use one column. Wider windows naturally expand
# to 2/3/4 columns when enough room is available.
CARD_TARGET_WIDTH = 560
CARD_MIN_WIDTH = 520
GRID_MIN_COLUMNS = 1
GRID_MAX_COLUMNS = 4

# The action controls remain inside the thumbnail overlay. Reserve a visual safe
# zone on both sides so a full-aspect vehicle image is rendered slightly smaller
# and centered, rather than being covered by left/right controls.
THUMBNAIL_SIDE_SAFE_PX = 48


def _columns_for_inner_width(inner_width: int) -> int:
    inner = max(1, int(inner_width))
    columns = inner // CARD_TARGET_WIDTH
    return max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, int(columns)))


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
    """v1.3.1 width sync with a one-column state and a real card minimum."""
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    host = getattr(self, f"{content_type}_grid_host", None)
    cards = getattr(self, f"_{content_type}_grid_cards", None)
    if scroll is None or layout is None or host is None or cards is None:
        return

    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return

    columns = max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, int(columns)))
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

    for column in range(GRID_MAX_COLUMNS):
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
    """Restore overlay actions and solve crowding through card/image geometry.

    This deliberately does not create side rails. Existing overlay controls stay
    where v1.3.2 placed them. The grid gains a true one-column state, cards get a
    larger minimum width, and the aspect-fit image is rendered inside a centered
    left/right safe zone so controls cannot cover the vehicle.
    """
    if getattr(MainWindow, "_fh6_v132_card_width_overlay_patched", False):
        return

    # v1.3's generalized layout function resolves this module-global helper at
    # runtime, so replacing it makes 1-column mode available without rewriting
    # the grouping/layout implementation.
    v13_ui._grid_column_count = _grid_column_count
    MainWindow._fh6_grid_column_count = _grid_column_count

    # v1.3.1 resize/reflow helpers also look up this module-global function at
    # runtime. Replace only the width calculation; keep its debounce/reflow code.
    v131_ui._apply_grid_card_widths = _apply_grid_card_widths

    original_make_card = MainWindow._make_saved_content_card

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        card.setMinimumWidth(CARD_MIN_WIDTH)
        policy = card.sizePolicy()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, policy.verticalPolicy())
        return card

    MainWindow._make_saved_content_card = patched_make_card

    # The global aspect controller already preserves the original image ratio.
    # Narrow only its effective render width. QLabel remains centered in the
    # original host, so the result is a smaller full image with transparent/
    # background space reserved under the overlay controls.
    if not getattr(_AspectFitThumbnailController, "_fh6_overlay_safe_width_patched", False):
        original_host_width = _AspectFitThumbnailController._host_width

        def safe_host_width(controller) -> int:
            return _safe_thumbnail_render_width(original_host_width(controller))

        _AspectFitThumbnailController._host_width = safe_host_width
        _AspectFitThumbnailController._fh6_overlay_safe_width_patched = True

    MainWindow._fh6_v132_card_width_overlay_patched = True
