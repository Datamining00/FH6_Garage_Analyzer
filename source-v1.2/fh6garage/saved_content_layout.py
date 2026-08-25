from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QLabel

from .i18n import tr
from .models import LiveryRecord
from . import ui_responsiveness as _responsive

GRID_TARGET_CARD_WIDTH = 420
GRID_MIN_COLUMNS = 2
GRID_MAX_COLUMNS = 4


def grid_column_count(self: Any, content_type: str) -> int:
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
    return max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, int(columns)))


def _current_grid_columns(self: Any, content_type: str) -> int:
    """Return the v1.3 responsive column count, with the release limits enforced."""
    counter = getattr(self, "_fh6_grid_column_count", None)
    if not callable(counter):
        return GRID_MIN_COLUMNS
    try:
        columns = int(counter(content_type))
    except (TypeError, ValueError, RuntimeError):
        return GRID_MIN_COLUMNS
    return max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, columns))


def _dynamic_layout_visible_grid_cards(
    self: Any,
    content_type: str,
    cards: list[QFrame],
) -> None:
    layout = (
        self.livery_grid_layout
        if content_type == "livery"
        else self.tuning_grid_layout
    )
    columns = _current_grid_columns(self, content_type)
    setattr(self, f"_fh6_{content_type}_grid_columns", columns)

    for column in range(GRID_MAX_COLUMNS):
        layout.setColumnStretch(column, 1 if column < columns else 0)

    if content_type == "livery":
        filtered: list[QFrame] = []
        for index, card in enumerate(cards):
            if _responsive._livery_visibility_allowed(self, card):
                filtered.append(card)
            _responsive._yield_busy_events(self, force=(index == 0))
        cards = filtered

    vehicle_group_button = getattr(self, f"{content_type}_group_button")
    creator_group_button = getattr(self, f"{content_type}_creator_group_button")
    group_by_vehicle = vehicle_group_button.isChecked()
    group_by_creator = creator_group_button.isChecked()

    if not group_by_vehicle and not group_by_creator:
        for index, card in enumerate(cards):
            layout.addWidget(card, index // columns, index % columns)
            card.setVisible(True)
            _responsive._yield_busy_events(self, force=(index == 0))
        return

    if group_by_creator:
        key_property = "creatorGroupKey"
        label_property = "creatorGroupLabel"
        fallback_label = tr("creator.none")
    else:
        key_property = "vehicleGroupKey"
        label_property = "vehicleGroupLabel"
        fallback_label = "Unknown vehicle"

    grouped: dict[str, list[QFrame]] = {}
    labels: dict[str, str] = {}
    for index, card in enumerate(cards):
        group_key = str(card.property(key_property) or "unknown")
        grouped.setdefault(group_key, []).append(card)
        labels.setdefault(
            group_key,
            str(card.property(label_property) or fallback_label),
        )
        _responsive._yield_busy_events(self, force=(index == 0))

    headers: dict[str, QLabel] = (
        self._livery_group_headers
        if content_type == "livery"
        else self._tuning_group_headers
    )
    noun = (
        tr("content.noun_livery")
        if content_type == "livery"
        else tr("content.noun_tuning")
    )

    row = 0
    item_index = 0
    for group_key, group_cards in grouped.items():
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
                    creator=labels[group_key],
                    noun=noun,
                    count=len(group_cards),
                )
            )
        else:
            header.setText(
                tr(
                    "content.group_header",
                    vehicle=labels[group_key],
                    noun=noun,
                    count=len(group_cards),
                )
            )

        layout.addWidget(header, row, 0, 1, columns)
        header.setVisible(True)
        row += 1
        _responsive._yield_busy_events(self, force=(item_index == 0))
        item_index += 1

        for index, card in enumerate(group_cards):
            layout.addWidget(
                card,
                row + index // columns,
                index % columns,
            )
            card.setVisible(True)
            _responsive._yield_busy_events(self)
            item_index += 1
        row += (len(group_cards) + columns - 1) // columns


def _dynamic_sync_grid_card_widths(self: Any, content_type: str) -> None:
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    cards = getattr(self, f"_{content_type}_grid_cards", None)
    host = getattr(self, f"{content_type}_grid_host", None)
    if scroll is None or layout is None or cards is None or host is None:
        return

    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return

    columns = _current_grid_columns(self, content_type)
    attr_name = f"_fh6_{content_type}_grid_columns"
    previous_columns = getattr(self, attr_name, None)
    setattr(self, attr_name, columns)

    for column in range(GRID_MAX_COLUMNS):
        layout.setColumnStretch(column, 1 if column < columns else 0)

    # A column-count transition changes row/column positions, so width-only
    # synchronization is insufficient. Relayout once, then the relayout path
    # returns here with the new count already stored and cannot recurse.
    if previous_columns is not None and previous_columns != columns:
        search = getattr(self, f"{content_type}_search", None)
        search_text = search.text() if search is not None else ""
        if content_type == "livery":
            self._relayout_livery_grid(search_text)
        else:
            self._relayout_tuning_grid(search_text)
        return

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
    for index, card in enumerate(cards):
        card.setMinimumWidth(0)
        card.setMaximumWidth(card_width)
        card.setFixedWidth(card_width)
        _responsive._yield_busy_events(self, force=(index == 0))

    host.setMinimumWidth(0)
    host.updateGeometry()
