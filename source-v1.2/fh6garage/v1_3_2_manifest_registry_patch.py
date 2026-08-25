from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt

from .auction_manifest_registry import read_auction_manifest_registry
from .auction_thumbnails import AuctionThumbnailManifestError, _header_livery_token
from .i18n import get_language
from .models import LiveryRecord

_AUCTION_UNAPPLIED_MODE = 13


def _registry_tooltip(key: str) -> str | None:
    ko = (get_language() or "ko").lower().startswith("ko")
    if key == "auction_applied_tip":
        return (
            "CacheThumbnails manifest 등록 목록에서 확인된 SoulBound 리버리 (WebP 생성 여부와 무관)"
            if ko
            else "SoulBound liveries present in the CacheThumbnails manifest registry, regardless of WebP hydration"
        )
    if key == "auction_unapplied_tip":
        return (
            "CacheThumbnails manifest 등록 목록에서 확인되지 않은 SoulBound 리버리"
            if ko
            else "SoulBound liveries absent from the CacheThumbnails manifest registry"
        )
    return None


def apply_v1_3_2_manifest_registry_patch(MainWindow) -> None:
    """Classify auction liveries from the manifest registry, not WebP hydration.

    CacheThumbnails has two distinct states:
      * registered logical names in the manifest's second table;
      * materialized GUID.webp files in the first table/on disk.

    Cache deletion can leave the full registered-name table intact while only a
    handful of WebPs are materialized. Therefore WebP existence is not a stable
    applied/unapplied signal. This patch keeps thumbnail resolution dependent on
    actual WebP files, but changes the UI applied-state classification to the
    registered logical-name table.
    """
    if getattr(MainWindow, "_fh6_v132_manifest_registry_patched", False):
        return

    original_populate_all = MainWindow._populate_all
    original_layout_visible_grid_cards = MainWindow._layout_visible_grid_cards
    original_filter_saved_content_table = MainWindow._filter_saved_content_table
    def rebuild_registry_state(self) -> None:
        self._fh6_v132_registered_auction_keys = set()
        self._fh6_v132_manifest_registry = None

        result = getattr(self, "result", None)
        if result is None:
            return

        cache_getter = getattr(self, "_fh6_v132_current_cache_path", None)
        cache_path = cache_getter() if callable(cache_getter) else None
        if cache_path is None:
            return

        try:
            registry = read_auction_manifest_registry(cache_path)
        except (AuctionThumbnailManifestError, OSError, ValueError):
            return

        registered_keys: set[str] = set()
        identities = registry.auction_identities
        for record in result.liveries:
            if (
                not isinstance(record, LiveryRecord)
                or record.kind != "SoulBoundLivery"
                or record.car_id is None
            ):
                continue
            token = _header_livery_token(record)
            if not token:
                continue
            if (int(record.car_id), token) in identities:
                registered_keys.add(
                    self._content_annotation_key("livery", record)
                )

        self._fh6_v132_registered_auction_keys = registered_keys
        self._fh6_v132_manifest_registry = registry

    def is_auction_applied(self, record: Any) -> bool:
        if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
            return False
        key = self._content_annotation_key("livery", record)
        return key in getattr(self, "_fh6_v132_registered_auction_keys", set())

    def patched_populate_all(self) -> None:
        # Must run before the existing population/filter layers so a valid
        # registered-but-not-yet-hydrated livery is not hidden as 'unapplied'.
        rebuild_registry_state(self)
        original_populate_all(self)

    def patched_layout_visible_grid_cards(
        self,
        content_type: str,
        cards,
    ) -> None:
        if (
            content_type == "livery"
            and _AUCTION_UNAPPLIED_MODE
            in self.livery_check_filter.selected_modes()
        ):
            filtered = []
            for card in cards:
                key = str(card.property("annotationKey") or "")
                record = (
                    self._record_for_content_key("livery", key)
                    if key
                    else None
                )
                if isinstance(record, LiveryRecord) and record.kind == "SoulBoundLivery":
                    if is_auction_applied(self, record):
                        continue
                filtered.append(card)
            cards = filtered
        original_layout_visible_grid_cards(self, content_type, cards)

    def patched_filter_saved_content_table(
        self,
        content_type: str,
        text: str,
    ) -> None:
        original_filter_saved_content_table(self, content_type, text)
        if (
            content_type != "livery"
            or _AUCTION_UNAPPLIED_MODE
            not in self.livery_check_filter.selected_modes()
        ):
            return

        table = self.livery_table
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            key_item = table.item(row, 0)
            key = (
                str(key_item.data(Qt.ItemDataRole.UserRole) or "")
                if key_item is not None
                else ""
            )
            record = (
                self._record_for_content_key("livery", key)
                if key
                else None
            )
            if (
                isinstance(record, LiveryRecord)
                and record.kind == "SoulBoundLivery"
                and is_auction_applied(self, record)
            ):
                table.setRowHidden(row, True)

    MainWindow._populate_all = patched_populate_all
    MainWindow._layout_visible_grid_cards = patched_layout_visible_grid_cards
    MainWindow._filter_saved_content_table = patched_filter_saved_content_table
    MainWindow._fh6_v132_rebuild_manifest_registry = rebuild_registry_state
    MainWindow._fh6_v132_is_auction_applied = is_auction_applied
    MainWindow._fh6_v132_manifest_registry_patched = True
