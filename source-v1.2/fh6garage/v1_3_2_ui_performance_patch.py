from __future__ import annotations

from pathlib import Path
from typing import Any

from .i18n import tr
from .models import LiveryRecord, TuningRecord
from .runtime_policy import detect_runtime_policy
from .saved_content_view import SortSpec, sort_cache_key
from .thumbnail_cache import ThumbnailPixmapCache


def _path_fingerprint(path: Any) -> tuple[str, int, int] | None:
    if path is None:
        return None
    try:
        candidate = Path(path)
        stat = candidate.stat()
    except (OSError, TypeError, ValueError):
        return None
    return (
        str(candidate).casefold(),
        int(stat.st_size),
        int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
    )


def _record_card_signature(
    self: Any,
    content_type: str,
    record: LiveryRecord | TuningRecord,
) -> tuple[Any, ...]:
    header = record.header
    raw_creator = (header.creator or "").strip()
    aliases = getattr(self, "creator_aliases", None)
    if aliases is not None and hasattr(aliases, "display_name"):
        try:
            creator_display = aliases.display_name(raw_creator)
        except Exception:  # noqa: BLE001 - third-party alias stores are optional
            creator_display = raw_creator
    else:
        creator_display = raw_creator
    return (
        content_type,
        getattr(record, "kind", "Tuning"),
        record.container_name,
        str(record.container_path).casefold(),
        header.version,
        header.name,
        header.description,
        raw_creator,
        creator_display,
        header.created,
        header.car_id,
        header.guid,
        header.decal_count,
        header.platform_code,
        self._car_label(record.car_id),
        record.downloaded_at,
        _path_fingerprint(record.thumbnail_path),
        _path_fingerprint(getattr(record, "livery_path", None)),
        _path_fingerprint(getattr(record, "data_path", None)),
        getattr(record, "content_sha256", ""),
        getattr(record, "data_size", 0),
    )


def _result_scope(result: Any) -> str:
    metadata = getattr(result, "metadata", None)
    root = getattr(metadata, "save_root", None)
    if root is None:
        return ""
    try:
        return str(Path(root).expanduser().resolve()).casefold()
    except OSError:
        return str(root).casefold()


def _records_for_result(
    result: Any,
) -> dict[str, list[LiveryRecord | TuningRecord]]:
    liveries = [
        record
        for record in getattr(result, "liveries", [])
        if isinstance(record, LiveryRecord)
        and record.kind in {"Livery", "SoulBoundLivery"}
    ]
    tunings = [
        record
        for record in getattr(result, "tunings", [])
        if isinstance(record, TuningRecord)
    ]
    return {"livery": liveries, "tuning": tunings}


def _cached_sorted_records(self: Any, content_type: str) -> list[Any]:
    factory = self._sorted_liveries if content_type == "livery" else self._sorted_tunings
    coordinator = getattr(self, "_view_operations", None)
    if coordinator is None or not hasattr(coordinator, "cached_order"):
        return list(factory())

    mode = getattr(self, f"_{content_type}_sort_mode", "default")
    descending = bool(getattr(self, f"_{content_type}_sort_descending", False))
    try:
        raw_records = self._saved_content_records(content_type)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        raw_records = ()
    cache_key = sort_cache_key(
        content_type=content_type,
        result=getattr(self, "result", None),
        records=raw_records,
        spec=SortSpec(mode=mode, descending=descending),
        initial_scan=bool(getattr(self, "_fh6_v132_initial_scan_build", False)),
        car_db_revision=int(getattr(getattr(self, "car_db", None), "revision", 0)),
        aliases=getattr(self, "creator_aliases", None),
    )
    return coordinator.cached_order(cache_key, factory)


def initialize_ui_performance_state(self: Any) -> None:
    """Initialize card/index caches without replacing ``MainWindow`` methods."""

    policy = detect_runtime_policy()
    self._fh6_runtime_policy = policy
    self._fh6_thumbnail_pixmap_cache = ThumbnailPixmapCache(
        policy.pixmap_cache_bytes
    )
    self._fh6_ui_cache_result_token = None
    self._fh6_ui_cache_scope = ""
    self._fh6_ui_record_signatures = {"livery": {}, "tuning": {}}
    self._fh6_ui_livery_cards_created = 0
    self._fh6_ui_livery_cards_reused = 0
    self._fh6_ui_tuning_cards_created = 0
    self._fh6_ui_tuning_cards_reused = 0
    self._fh6_ui_cards_discarded = 0
    self._fh6_record_by_key = {"livery": {}, "tuning": {}}
    self._fh6_record_index_ready = False


def _delete_group_headers(self: Any) -> None:
    for name in ("_livery_group_headers", "_tuning_group_headers"):
        headers = getattr(self, name, None)
        if not isinstance(headers, dict):
            continue
        for header in list(headers.values()):
            try:
                header.hide()
                header.deleteLater()
            except RuntimeError:
                pass
        headers.clear()


def _delete_card(card: Any) -> None:
    try:
        card.hide()
        card.deleteLater()
    except RuntimeError:
        pass


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


def _delete_cached_cards(self: Any, *, clear_pixmaps: bool = False) -> None:
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
        _delete_card(card)

    self._livery_grid_cards.clear()
    self._livery_card_by_key.clear()
    self._tuning_grid_cards.clear()
    self._tuning_card_by_key.clear()
    _delete_group_headers(self)
    self._fh6_ui_record_signatures = {"livery": {}, "tuning": {}}
    if clear_pixmaps:
        pixmaps = getattr(self, "_fh6_thumbnail_pixmap_cache", None)
        if pixmaps is not None and hasattr(pixmaps, "clear"):
            pixmaps.clear()


def _reconcile_cached_cards(self: Any, result: Any) -> None:
    records = _records_for_result(result)
    previous = getattr(
        self,
        "_fh6_ui_record_signatures",
        {"livery": {}, "tuning": {}},
    )
    next_signatures: dict[str, dict[str, tuple[Any, ...]]] = {
        "livery": {},
        "tuning": {},
    }

    for content_type, content_records in records.items():
        cache = getattr(self, f"_{content_type}_card_by_key", {})
        for record in content_records:
            key = self._content_annotation_key(content_type, record)
            next_signatures[content_type][key] = _record_card_signature(
                self,
                content_type,
                record,
            )

        old_signatures = previous.get(content_type, {})
        for key, card in list(cache.items()):
            if (
                key not in next_signatures[content_type]
                or old_signatures.get(key) != next_signatures[content_type][key]
            ):
                cache.pop(key, None)
                _delete_card(card)
                self._fh6_ui_cards_discarded += 1

    # Group headers are inexpensive but their keys and displayed aliases can
    # become stale across rescans.  Rebuild headers while preserving cards.
    _delete_group_headers(self)
    self._fh6_ui_record_signatures = next_signatures


def _ensure_scan_generation(self: Any) -> None:
    result = getattr(self, "result", None)
    token = id(result) if result is not None else None
    if token == getattr(self, "_fh6_ui_cache_result_token", None):
        return

    view_operations = getattr(self, "_view_operations", None)
    if view_operations is not None and hasattr(view_operations, "clear_order_cache"):
        view_operations.clear_order_cache()

    old_token = getattr(self, "_fh6_ui_cache_result_token", None)
    old_scope = getattr(self, "_fh6_ui_cache_scope", "")
    new_scope = _result_scope(result)
    if old_token is not None and old_scope and new_scope and old_scope != new_scope:
        _delete_cached_cards(self, clear_pixmaps=True)
        if hasattr(result, "liveries") and hasattr(result, "tunings"):
            _reconcile_cached_cards(self, result)
    elif old_token is not None:
        if hasattr(result, "liveries") and hasattr(result, "tunings"):
            # Detach every old layout item before removing changed widgets.
            if hasattr(self, "_clear_livery_grid_layout"):
                self._clear_livery_grid_layout()
            if hasattr(self, "_clear_tuning_grid_layout"):
                self._clear_tuning_grid_layout()
            _reconcile_cached_cards(self, result)
        else:
            # Compatibility path for third-party/test result objects that do
            # not provide the v1.3.2 ScanResult contract.
            _delete_cached_cards(self)
    elif hasattr(result, "liveries") and hasattr(result, "tunings"):
        _reconcile_cached_cards(self, result)

    self._fh6_ui_cache_result_token = token
    self._fh6_ui_cache_scope = new_scope


def _populate_livery_grid_reusing_cards(self: Any) -> None:
    """Reorder/reuse livery cards instead of deleting and recreating them."""
    _ensure_scan_generation(self)

    ordered_cards: list[Any] = []
    active_keys: set[str] = set()
    cache = self._livery_card_by_key

    for index, record in enumerate(_cached_sorted_records(self, "livery")):
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

    for index, record in enumerate(_cached_sorted_records(self, "tuning")):
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
    view.  This patch keeps unchanged card widgets alive across sorting,
    filtering and same-save refreshes, then uses the existing relayout/filter
    code for subsequent interactions.
    """
    if getattr(MainWindow, "_fh6_v132_ui_performance_patched", False):
        return

    original_init = MainWindow.__init__
    original_populate_all = MainWindow._populate_all
    original_record_for_content_key = MainWindow._record_for_content_key

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        initialize_ui_performance_state(self)

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

    def patched_record_for_content_key(self, content_type: str, key: str):
        if getattr(self, "_fh6_record_index_ready", False):
            indexes = getattr(self, "_fh6_record_by_key", {})
            index = indexes.get(content_type) if isinstance(indexes, dict) else None
            if isinstance(index, dict):
                return index.get(key)
        return original_record_for_content_key(self, content_type, key)

    MainWindow.__init__ = patched_init
    MainWindow._populate_all = patched_populate_all
    MainWindow._populate_livery_grid = _populate_livery_grid_reusing_cards
    MainWindow._populate_tuning_grid = _populate_tuning_grid_reusing_cards
    MainWindow._populate_livery_table = patched_populate_livery_table
    MainWindow._populate_tuning_table = patched_populate_tuning_table
    MainWindow._record_for_content_key = patched_record_for_content_key

    MainWindow._fh6_v132_reset_ui_card_cache = _delete_cached_cards
    MainWindow._fh6_v132_ensure_ui_scan_generation = _ensure_scan_generation
    MainWindow._fh6_v132_ui_performance_patched = True
