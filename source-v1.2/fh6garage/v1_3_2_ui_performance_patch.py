from __future__ import annotations

from typing import Any

from .i18n import tr
from .models import LiveryRecord, TuningRecord


def _configure_card_properties(
    self: Any,
    content_type: str,
    record: LiveryRecord | TuningRecord,
    key: str,
    card: Any,
) -> None:
    """Refresh the lightweight properties used by search/filter/group layout.

    The actual card widget is intentionally kept alive.  Sort/source/filter
    changes only alter ordering or visibility, so recreating the complete Qt
    widget tree is unnecessary and was the dominant v1.3.2 runtime cost.
    """
    annotation = self.annotations.get(key)
    if content_type == "livery":
        search_text = self._livery_search_text(record, annotation.note)
    else:
        search_text = self._saved_content_search_text(record, annotation.note)

    card.setProperty("searchText", search_text)
    card.setProperty("annotationKey", key)
    card.setProperty(
        "vehicleGroupKey",
        f"id:{record.car_id}" if record.car_id is not None else "unknown",
    )
    card.setProperty("vehicleGroupLabel", self._car_label(record.car_id))

    creator_label = (record.header.creator or "").strip() or tr("creator.none")
    card.setProperty(
        "creatorGroupKey",
        f"creator:{creator_label.casefold()}",
    )
    card.setProperty("creatorGroupLabel", creator_label)
    card.setProperty("checked", annotation.checked)
    card.setProperty("triangle", annotation.triangle)
    card.setProperty("excluded", annotation.excluded)


def _delete_cached_cards(self: Any) -> None:
    """Drop cached widgets only when a genuinely new ScanResult is installed."""
    # Invalidate a deferred SoulBound append from the previous scan first.
    self._fh6_v132_auction_build_generation = (
        getattr(self, "_fh6_v132_auction_build_generation", 0) + 1
    )

    if hasattr(self, "_clear_livery_grid_layout"):
        self._clear_livery_grid_layout()
    if hasattr(self, "_clear_tuning_grid_layout"):
        self._clear_tuning_grid_layout()

    seen: set[int] = set()
    card_groups = (
        list(getattr(self, "_livery_card_by_key", {}).values())
        + list(getattr(self, "_livery_grid_cards", []))
        + list(getattr(self, "_tuning_card_by_key", {}).values())
        + list(getattr(self, "_tuning_grid_cards", []))
    )
    for card in card_groups:
        marker = id(card)
        if marker in seen:
            continue
        seen.add(marker)
        card.hide()
        card.deleteLater()

    self._livery_grid_cards.clear()
    self._livery_card_by_key.clear()
    self._tuning_grid_cards.clear()
    self._tuning_card_by_key.clear()


def _ensure_scan_generation(self: Any) -> None:
    result = getattr(self, "result", None)
    token = id(result) if result is not None else None
    if token == getattr(self, "_fh6_ui_cache_result_token", None):
        return
    _delete_cached_cards(self)
    self._fh6_ui_cache_result_token = token


def _populate_livery_grid_reusing_cards(self: Any) -> None:
    """Reorder/reuse livery cards instead of deleting and recreating them."""
    _ensure_scan_generation(self)

    ordered_cards: list[Any] = []
    active_keys: set[str] = set()
    cache = self._livery_card_by_key

    for index, record in enumerate(self._sorted_liveries()):
        self._keep_busy_responsive(index)
        key = self._annotation_key(record)
        active_keys.add(key)

        card = cache.get(key)
        if card is None:
            card = self._make_livery_card(record, key)
            # Parent immediately.  This preserves the v1.3.2 Windows safety
            # rule used for deferred SoulBound cards as well.
            card.setParent(self.livery_grid_host)
            card.hide()
            cache[key] = card
            self._fh6_ui_livery_cards_created += 1
        else:
            self._fh6_ui_livery_cards_reused += 1

        _configure_card_properties(self, "livery", record, key, card)
        ordered_cards.append(card)

    # Cards belonging to a currently disabled source stay cached for an instant
    # My Designs/Auction toggle, but are hidden and release any large thumbnail.
    for key, card in list(cache.items()):
        if key in active_keys:
            continue
        card.hide()
        unload = getattr(self, "_unload_livery_card_thumbnail", None)
        if callable(unload):
            unload(card)

    self._livery_grid_cards[:] = ordered_cards

    # _relayout_livery_grid() already clears the old layout, applies search and
    # status filters, repacks groups, synchronizes widths, and schedules lazy
    # thumbnail loading.  Do it exactly once per rebuild.
    self._relayout_livery_grid(self.livery_search.text())


def _populate_tuning_grid_reusing_cards(self: Any) -> None:
    _ensure_scan_generation(self)

    ordered_cards: list[Any] = []
    active_keys: set[str] = set()
    cache = self._tuning_card_by_key

    for index, record in enumerate(self._sorted_tunings()):
        self._keep_busy_responsive(index)
        key = self._content_annotation_key("tuning", record)
        active_keys.add(key)

        card = cache.get(key)
        if card is None:
            card = self._make_tuning_card(record, key)
            card.setParent(self.tuning_grid_host)
            card.hide()
            cache[key] = card
            self._fh6_ui_tuning_cards_created += 1
        else:
            self._fh6_ui_tuning_cards_reused += 1

        _configure_card_properties(self, "tuning", record, key, card)
        ordered_cards.append(card)

    for key, card in list(cache.items()):
        if key in active_keys:
            continue
        card.hide()
        unload = getattr(self, "_unload_livery_card_thumbnail", None)
        if callable(unload):
            unload(card)

    self._tuning_grid_cards[:] = ordered_cards
    self._relayout_tuning_grid(self.tuning_search.text())


def apply_v1_3_2_ui_performance_patches(MainWindow) -> None:
    """Reduce v1.3.2 GUI rebuild cost without changing save-data behavior.

    Performance reports showed that sorting 630 liveries rebuilt 630 complete
    card widget trees every time.  The hidden legacy QTableWidget was also
    repopulated although the v1.3 grid UI is the only user-facing saved-content
    view.  This patch keeps card widgets alive for the lifetime of one ScanResult
    and uses the existing relayout/filter code for subsequent interactions.
    """
    if getattr(MainWindow, "_fh6_v132_ui_performance_patched", False):
        return

    original_init = MainWindow.__init__
    original_populate_all = MainWindow._populate_all

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self._fh6_ui_cache_result_token = None
        self._fh6_ui_livery_cards_created = 0
        self._fh6_ui_livery_cards_reused = 0
        self._fh6_ui_tuning_cards_created = 0
        self._fh6_ui_tuning_cards_reused = 0

    def patched_populate_all(self) -> None:
        # A new ScanResult invalidates cached widgets.  Sorting, filtering,
        # grouping, annotation changes and source toggles do not.
        _ensure_scan_generation(self)
        original_populate_all(self)

    def patched_populate_livery_table(self) -> None:
        # Explicit sort/source rebuilds must cancel any older deferred auction
        # append before changing the active card ordering.
        self._fh6_v132_auction_build_generation = (
            getattr(self, "_fh6_v132_auction_build_generation", 0) + 1
        )

        # livery_table is a hidden legacy view in v1.3.2.  Building hundreds of
        # QTableWidget rows cost ~1 s per sort in the measured dataset and does
        # not contribute to the visible grid.  Annotation synchronization is
        # already card-first and safely tolerates an empty hidden table.
        _populate_livery_grid_reusing_cards(self)

    def patched_populate_tuning_table(self) -> None:
        # Same rule for the hidden tuning table.  The visible tuning grid remains
        # fully populated and uses the existing search/filter/annotation paths.
        _populate_tuning_grid_reusing_cards(self)

    MainWindow.__init__ = patched_init
    MainWindow._populate_all = patched_populate_all
    MainWindow._populate_livery_grid = _populate_livery_grid_reusing_cards
    MainWindow._populate_tuning_grid = _populate_tuning_grid_reusing_cards
    MainWindow._populate_livery_table = patched_populate_livery_table
    MainWindow._populate_tuning_table = patched_populate_tuning_table

    MainWindow._fh6_v132_reset_ui_card_cache = _delete_cached_cards
    MainWindow._fh6_v132_ensure_ui_scan_generation = _ensure_scan_generation
    MainWindow._fh6_v132_ui_performance_patched = True
