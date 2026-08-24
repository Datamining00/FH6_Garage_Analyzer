from __future__ import annotations

from typing import Any

from . import v1_3_ui_patch as v13_ui
from . import v1_3_1_patch as v131


GRID_MIN_COLUMNS = 2
GRID_TARGET_CARD_WIDTH = 420


def _unbounded_grid_column_count(self: Any, content_type: str) -> int:
    """Return a responsive column count with a 2-column floor and no ceiling."""
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
    columns = inner_width // GRID_TARGET_CARD_WIDTH
    return max(GRID_MIN_COLUMNS, int(columns))


def _apply_unbounded_grid_card_widths(
    self: Any,
    content_type: str,
    columns: int,
    *,
    force: bool = False,
) -> None:
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
    card_width = max(1, available // columns)

    last_attr = f"_fh6_v131_{content_type}_card_width"
    last_width = getattr(self, last_attr, None)
    if (
        not force
        and isinstance(last_width, int)
        and abs(card_width - last_width) < v131.CARD_WIDTH_UPDATE_STEP
    ):
        return

    seen_attr = f"_fh6_v132_{content_type}_max_grid_columns_seen"
    previous_seen = getattr(self, seen_attr, GRID_MIN_COLUMNS)
    stretch_limit = max(4, int(previous_seen), columns)
    for column in range(stretch_limit):
        stretch = 1 if column < columns else 0
        if layout.columnStretch(column) != stretch:
            layout.setColumnStretch(column, stretch)
    setattr(self, seen_attr, max(int(previous_seen), columns))

    for card in cards:
        if card.minimumWidth() != card_width or card.maximumWidth() != card_width:
            card.setFixedWidth(card_width)

    setattr(self, last_attr, card_width)
    host.setMinimumWidth(0)
    host.updateGeometry()


def apply_v1_3_2_unbounded_grid_patch(MainWindow) -> None:
    """Remove the legacy four-column ceiling while preserving a two-column floor.

    v1.3 introduced a 2..4 column clamp and v1.3.1 repeated the same clamp in
    its lightweight resize path. Both functions are module globals referenced at
    call time, so replacing them here upgrades normal layout, resize reflow and
    first-paint stabilization consistently without rewriting those proven paths.
    """
    if getattr(MainWindow, "_fh6_v132_unbounded_grid_patched", False):
        return

    v13_ui._grid_column_count = _unbounded_grid_column_count
    v131._apply_grid_card_widths = _apply_unbounded_grid_card_widths
    MainWindow._fh6_grid_column_count = _unbounded_grid_column_count

    MainWindow._fh6_v132_unbounded_grid_patched = True
