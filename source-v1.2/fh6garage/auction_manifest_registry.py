from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

from .auction_thumbnails import (
    AuctionThumbnailManifestError,
    _MAX_NAME_LENGTH,
    _MAX_RECORDS,
    _MANIFEST_VERSION,
    _read_manifest_bytes,
)


_REGISTRY_VERSION = 1
_LOGICAL_NAME_RE = re.compile(
    r"^(?P<car_id>\d+)_(?P<instance_key>[0-9a-f]{16})"
    r"(?P<appearance>bm\d+|u(?P<livery_token>[0-9a-z]{26}))"
    r"_bigThumb\.webp$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AuctionManifestRegistry:
    logical_names: frozenset[str]
    auction_identities: frozenset[tuple[int, str]]
    generation_id: int = 0


def _checked_name_length(data: bytes, offset: int, index: int, table: str) -> tuple[int, int]:
    if offset + 4 > len(data):
        raise AuctionThumbnailManifestError(
            f"manifest ended before {table} record {index} length"
        )
    name_length = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if name_length <= 0 or name_length > _MAX_NAME_LENGTH:
        raise AuctionThumbnailManifestError(
            f"invalid {table} logical name length at record {index}: {name_length}"
        )
    return name_length, offset


def read_auction_manifest_registry(cache_dir: Path) -> AuctionManifestRegistry:
    """Read the manifest's registered logical-name table.

    FH6 CacheThumbnails manifests contain a second logical-name table after the
    GUID/WebP materialization table. Two captures taken before and after cache
    hydration showed that this table remains stable while the first table grows
    from only the currently materialized WebPs to the full cache set.

    This parser deliberately stops after the registered-name table. The trailing
    materialized-name table is not required for applied/unapplied classification.
    """
    cache_dir = Path(cache_dir)
    data = _read_manifest_bytes(cache_dir / ".manifest")

    if len(data) < 8:
        raise AuctionThumbnailManifestError("manifest is too small")

    version, count = struct.unpack_from("<II", data, 0)
    if version != _MANIFEST_VERSION:
        raise AuctionThumbnailManifestError(
            f"unsupported CacheThumbnails manifest version: {version}"
        )
    if count > _MAX_RECORDS:
        raise AuctionThumbnailManifestError(
            f"unreasonable manifest record count: {count}"
        )

    # Skip first table: length + UTF-8 logical name + 16-byte Windows GUID.
    offset = 8
    for index in range(count):
        name_length, offset = _checked_name_length(data, offset, index, "GUID")
        end_record = offset + name_length + 16
        if end_record > len(data):
            raise AuctionThumbnailManifestError(
                f"manifest ended inside GUID record {index}"
            )
        offset = end_record

    # Observed second-table header:
    #   uint32 registry_version (=1)
    #   uint64 stable generation/cache identifier
    #   uint32 logical-name count
    if offset + 16 > len(data):
        raise AuctionThumbnailManifestError("manifest has no registered-name table")

    registry_version = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if registry_version != _REGISTRY_VERSION:
        raise AuctionThumbnailManifestError(
            f"unsupported registered-name table version: {registry_version}"
        )

    generation_id = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    registered_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if registered_count > _MAX_RECORDS:
        raise AuctionThumbnailManifestError(
            f"unreasonable registered-name count: {registered_count}"
        )

    logical_names: set[str] = set()
    identities: set[tuple[int, str]] = set()

    for index in range(registered_count):
        name_length, offset = _checked_name_length(
            data, offset, index, "registered"
        )
        end_name = offset + name_length
        if end_name > len(data):
            raise AuctionThumbnailManifestError(
                f"manifest ended inside registered-name record {index}"
            )
        try:
            logical_name = data[offset:end_name].decode("utf-8")
        except UnicodeDecodeError:
            offset = end_name
            continue
        offset = end_name
        logical_names.add(logical_name)

        match = _LOGICAL_NAME_RE.match(logical_name)
        if match is None:
            continue
        token = (match.group("livery_token") or "").lower()
        if not token:
            continue
        try:
            car_id = int(match.group("car_id"))
        except ValueError:
            continue
        identities.add((car_id, token))

    return AuctionManifestRegistry(
        logical_names=frozenset(logical_names),
        auction_identities=frozenset(identities),
        generation_id=generation_id,
    )
