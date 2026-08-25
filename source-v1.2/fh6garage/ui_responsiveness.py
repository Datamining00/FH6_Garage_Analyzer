from __future__ import annotations

from time import perf_counter
from typing import Any

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from .i18n import tr
from .models import LiveryRecord

_BUSY_YIELD_INTERVAL_SECONDS = 1.0 / 60.0
_BUSY_PROCESS_EVENTS_MS = 4
_HIDDEN_MODE = 11
_AUCTION_APPLIED_MODE = 12
_AUCTION_UNAPPLIED_MODE = 13


def _yield_busy_events(self: Any, force: bool = False) -> None:
    if not getattr(self, "_busy_depth", 0):
        return
    if getattr(self, "_fh6_busy_event_pump_active", False):
        return

    now = perf_counter()
    last = float(getattr(self, "_fh6_busy_last_yield", 0.0) or 0.0)
    if not force and last and (now - last) < _BUSY_YIELD_INTERVAL_SECONDS:
        return

    self._fh6_busy_last_yield = now
    overlay = getattr(self, "_busy_overlay", None)
    if overlay is not None:
        overlay.update()
        message = getattr(overlay, "message", None)
        if message is not None:
            message.update()
        progress = getattr(overlay, "progress", None)
        if progress is not None:
            progress.update()

    self._fh6_busy_event_pump_active = True
    try:
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
            _BUSY_PROCESS_EVENTS_MS,
        )
    finally:
        self._fh6_busy_event_pump_active = False
        self._fh6_busy_last_yield = perf_counter()


def _responsive_keep_busy(self: Any, index: int = 0, interval: int = 12) -> None:
    _yield_busy_events(self, force=(index == 0))


def _responsive_clear_grid_layout(self: Any, content_type: str) -> None:
    layout = self.livery_grid_layout if content_type == "livery" else self.tuning_grid_layout
    headers = self._livery_group_headers if content_type == "livery" else self._tuning_group_headers

    index = 0
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setVisible(False)
        _yield_busy_events(self, force=(index == 0))
        index += 1

    for index, header in enumerate(headers.values()):
        header.setVisible(False)
        _yield_busy_events(self, force=(index == 0 and not layout.count()))


def _livery_visibility_allowed(self: Any, card: Any) -> bool:
    key = str(card.property("annotationKey") or "")
    is_hidden = getattr(self, "_fh6_v132_is_livery_hidden", None)
    hidden = bool(is_hidden(key)) if key and callable(is_hidden) else False
    modes = self.livery_check_filter.selected_modes()

    if _HIDDEN_MODE in modes:
        if not hidden:
            return False
    elif hidden:
        return False

    applied_filter = _AUCTION_APPLIED_MODE in modes
    unapplied_filter = _AUCTION_UNAPPLIED_MODE in modes
    if applied_filter or unapplied_filter:
        record = self._record_for_content_key("livery", key) if key else None
        if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
            return False
        applied_fn = getattr(self, "_fh6_v132_is_auction_applied", None)
        applied = bool(applied_fn(record)) if callable(applied_fn) else False
        if applied_filter and not applied:
            return False
        if unapplied_filter and applied:
            return False

    return True


def _responsive_layout_visible_grid_cards(self: Any, content_type: str, cards: list[QFrame]) -> None:
    layout = self.livery_grid_layout if content_type == "livery" else self.tuning_grid_layout

    if content_type == "livery":
        filtered: list[QFrame] = []
        for index, card in enumerate(cards):
            if _livery_visibility_allowed(self, card):
                filtered.append(card)
            _yield_busy_events(self, force=(index == 0))
        cards = filtered

    vehicle_group_button = getattr(self, f"{content_type}_group_button")
    creator_group_button = getattr(self, f"{content_type}_creator_group_button")
    group_by_vehicle = vehicle_group_button.isChecked()
    group_by_creator = creator_group_button.isChecked()

    if not group_by_vehicle and not group_by_creator:
        for index, card in enumerate(cards):
            layout.addWidget(card, index // 2, index % 2)
            card.setVisible(True)
            _yield_busy_events(self, force=(index == 0))
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
        labels.setdefault(group_key, str(card.property(label_property) or fallback_label))
        _yield_busy_events(self, force=(index == 0))

    headers: dict[str, QLabel] = self._livery_group_headers if content_type == "livery" else self._tuning_group_headers
    noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")
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
            header.setText(tr("content.creator_group_header", creator=labels[group_key], noun=noun, count=len(group_cards)))
        else:
            header.setText(tr("content.group_header", vehicle=labels[group_key], noun=noun, count=len(group_cards)))
        layout.addWidget(header, row, 0, 1, 2)
        header.setVisible(True)
        row += 1
        _yield_busy_events(self, force=(item_index == 0))
        item_index += 1

        for index, card in enumerate(group_cards):
            layout.addWidget(card, row + index // 2, index % 2)
            card.setVisible(True)
            _yield_busy_events(self)
            item_index += 1
        row += (len(group_cards) + 1) // 2


def _schedule_grid_followup(self: Any, content_type: str) -> None:
    """Coalesce width/thumbnail callbacks generated by one UI event burst."""

    pending_name = f"_fh6_{content_type}_grid_followup_pending"
    if getattr(self, pending_name, False):
        return
    setattr(self, pending_name, True)

    def run() -> None:
        setattr(self, pending_name, False)
        if content_type == "livery":
            self._sync_livery_grid_card_widths()
            self._refresh_visible_livery_thumbnails()
        else:
            self._sync_tuning_grid_card_widths()
            self._refresh_visible_tuning_thumbnails()

    QTimer.singleShot(0, run)


def _responsive_relayout_livery_grid(self: Any, text: str = "") -> None:
    needle = text.strip().lower()
    self.livery_grid_host.setUpdatesEnabled(False)
    try:
        _responsive_clear_grid_layout(self, "livery")
        visible_cards: list[QFrame] = []
        for index, card in enumerate(self._livery_grid_cards):
            haystack = str(card.property("searchText") or "")
            checked = bool(card.property("checked"))
            triangle = bool(card.property("triangle"))
            excluded = bool(card.property("excluded"))
            key = str(card.property("annotationKey") or "")
            note = self.annotations.get(key).note if key else ""
            record = self._record_for_content_key("livery", key) if key else None
            duplicate = self._is_duplicate_livery(record if isinstance(record, LiveryRecord) else None)
            matched = (not needle or needle in haystack) and self._livery_filter_matches(checked, note, triangle, excluded, duplicate)
            if not matched:
                self._unload_livery_card_thumbnail(card)
            else:
                visible_cards.append(card)
            _yield_busy_events(self, force=(index == 0))

        _responsive_layout_visible_grid_cards(self, "livery", visible_cards)
        self.livery_grid_layout.activate()
    finally:
        self.livery_grid_host.setUpdatesEnabled(True)
    self.livery_grid_host.update()

    self._sync_livery_grid_card_widths()
    _schedule_grid_followup(self, "livery")
    _yield_busy_events(self, force=True)


def _responsive_relayout_tuning_grid(self: Any, text: str = "") -> None:
    needle = text.strip().lower()
    self.tuning_grid_host.setUpdatesEnabled(False)
    try:
        _responsive_clear_grid_layout(self, "tuning")
        visible_cards: list[QFrame] = []
        for index, card in enumerate(self._tuning_grid_cards):
            haystack = str(card.property("searchText") or "")
            checked = bool(card.property("checked"))
            triangle = bool(card.property("triangle"))
            excluded = bool(card.property("excluded"))
            key = str(card.property("annotationKey") or "")
            note = self.annotations.get(key).note if key else ""
            matched = (not needle or needle in haystack) and self._saved_content_filter_matches("tuning", checked, note, triangle, excluded)
            if not matched:
                self._unload_livery_card_thumbnail(card)
            else:
                visible_cards.append(card)
            _yield_busy_events(self, force=(index == 0))

        _responsive_layout_visible_grid_cards(self, "tuning", visible_cards)
        self.tuning_grid_layout.activate()
    finally:
        self.tuning_grid_host.setUpdatesEnabled(True)
    self.tuning_grid_host.update()

    self._sync_tuning_grid_card_widths()
    _schedule_grid_followup(self, "tuning")
    _yield_busy_events(self, force=True)


def _responsive_sync_grid_card_widths(self: Any, content_type: str) -> None:
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    cards = getattr(self, f"_{content_type}_grid_cards", None)
    host = getattr(self, f"{content_type}_grid_host", None)
    if scroll is None or layout is None or cards is None or host is None:
        return

    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return
    margins = layout.contentsMargins()
    gap = max(0, layout.horizontalSpacing())
    available = viewport.width() - margins.left() - margins.right() - gap - 4
    card_width = max(1, available // 2)
    for index, card in enumerate(cards):
        card.setMinimumWidth(0)
        card.setMaximumWidth(card_width)
        card.setFixedWidth(card_width)
        _yield_busy_events(self, force=(index == 0))
    host.setMinimumWidth(0)
    host.updateGeometry()


def _install_download_sort_default(MainWindow: Any) -> None:
    original = MainWindow._set_saved_content_sort_mode

    def patched(self: Any, content_type: str, mode: str) -> None:
        if content_type in {"livery", "tuning"} and mode == "download":
            mode_attr = "_livery_sort_mode" if content_type == "livery" else "_tuning_sort_mode"
            descending_attr = "_livery_sort_descending" if content_type == "livery" else "_tuning_sort_descending"
            if getattr(self, mode_attr, "__initial__") != "download":
                setattr(self, mode_attr, "download")
                setattr(self, descending_attr, False)
        original(self, content_type, mode)

    MainWindow._set_saved_content_sort_mode = patched

