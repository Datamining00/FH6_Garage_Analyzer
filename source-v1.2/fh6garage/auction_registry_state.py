from __future__ import annotations

from pathlib import Path
from typing import Any

from .auction_manifest_registry import read_auction_manifest_registry
from .auction_thumbnails import AuctionThumbnailManifestError, _header_livery_token
from .models import LiveryRecord


def rebuild_auction_registry_state(owner: Any, cache_path: Path | None) -> None:
    """Build the applied-auction key set from the manifest logical registry."""
    owner._fh6_v132_registered_auction_keys = set()
    owner._fh6_v132_manifest_registry = None
    result = getattr(owner, "result", None)
    if result is None or cache_path is None:
        return
    try:
        registry = read_auction_manifest_registry(cache_path)
    except (AuctionThumbnailManifestError, OSError, ValueError):
        return

    identities = registry.auction_identities
    registered_keys: set[str] = set()
    for record in result.liveries:
        if (
            not isinstance(record, LiveryRecord)
            or record.kind != "SoulBoundLivery"
            or record.car_id is None
        ):
            continue
        token = _header_livery_token(record)
        if token and (int(record.car_id), token) in identities:
            registered_keys.add(owner._content_annotation_key("livery", record))

    owner._fh6_v132_registered_auction_keys = registered_keys
    owner._fh6_v132_manifest_registry = registry


def is_auction_livery_registered(owner: Any, record: object) -> bool:
    if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
        return False
    key = owner._content_annotation_key("livery", record)
    return key in getattr(owner, "_fh6_v132_registered_auction_keys", set())
