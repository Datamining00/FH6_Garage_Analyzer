from __future__ import annotations

import os
import re
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import LiveryRecord


_MANIFEST_VERSION = 2
_MAX_RECORDS = 1_000_000
_MAX_NAME_LENGTH = 4096
_MANIFEST_READ_ATTEMPTS = 3
_MANIFEST_READ_DELAY_SECONDS = 0.05
_CROCKFORD32 = "0123456789abcdefghjkmnpqrstvwxyz"

_LOGICAL_NAME_RE = re.compile(
    r"^(?P<car_id>\d+)_(?P<instance_key>[0-9a-f]{16})"
    r"(?P<appearance>bm\d+|u(?P<livery_token>[0-9a-z]{26}))"
    r"_bigThumb\.webp$",
    re.IGNORECASE,
)
_CONTAINER_TIME_RE = re.compile(r"_(?P<stamp>\d{14})$")


class AuctionThumbnailManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ManifestThumbnailEntry:
    index: int
    logical_name: str
    car_id: int
    guid: str
    path: Path
    instance_key: str = ""
    livery_token: str = ""


@dataclass(frozen=True, slots=True)
class AuctionThumbnailMatchStats:
    auction_count: int = 0
    matched_by_header_id: int = 0
    ambiguous: int = 0
    unmatched: int = 0

    @property
    def matched(self) -> int:
        return self.matched_by_header_id

    # Compatibility with the first v1.3.2 work build. Time/order matching was
    # removed once the header-token relationship was verified.
    @property
    def matched_by_time(self) -> int:
        return 0

    @property
    def matched_by_order(self) -> int:
        return 0


def is_thumbnail_cache_dir(path: Path | str | None) -> bool:
    if path is None:
        return False
    try:
        candidate = Path(path).expanduser()
    except (TypeError, ValueError):
        return False
    return candidate.is_dir() and (candidate / ".manifest").is_file()


def auto_detect_thumbnail_cache(local_appdata: Path | None = None) -> Optional[Path]:
    """Locate an FH6 CacheThumbnails directory only after .manifest validation."""
    if local_appdata is None:
        raw = os.environ.get("LOCALAPPDATA", "").strip()
        if not raw:
            return None
        local_appdata = Path(raw)

    local_appdata = Path(local_appdata)
    relative = (
        Path("LocalCache")
        / "Local"
        / "LocalStorage_Cache"
        / "CacheThumbnails"
    )

    candidates: list[Path] = [
        local_appdata
        / "Packages"
        / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
        / relative,
        local_appdata
        / "ForzaHorizon6"
        / "LocalStorage_Cache"
        / "CacheThumbnails",
    ]

    # Fallback for alternate Microsoft package names. Only immediate package
    # directories are inspected; AppData is never recursively scanned.
    packages = local_appdata / "Packages"
    if packages.is_dir():
        try:
            package_dirs = sorted(
                (
                    path
                    for path in packages.iterdir()
                    if path.is_dir() and path.name.startswith("Microsoft.")
                ),
                key=lambda path: path.name.casefold(),
            )
        except OSError:
            package_dirs = []
        for package in package_dirs:
            candidates.append(package / relative)

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if is_thumbnail_cache_dir(candidate):
            return candidate
    return None


def _read_manifest_bytes(path: Path) -> bytes:
    last_error: OSError | None = None
    for attempt in range(_MANIFEST_READ_ATTEMPTS):
        try:
            return path.read_bytes()
        except OSError as exc:
            last_error = exc
            if attempt + 1 < _MANIFEST_READ_ATTEMPTS:
                time.sleep(_MANIFEST_READ_DELAY_SECONDS)
    raise AuctionThumbnailManifestError(str(last_error or "manifest read failed"))


def read_thumbnail_manifest(cache_dir: Path) -> list[ManifestThumbnailEntry]:
    """Read only the verified first table of CacheThumbnails/.manifest."""
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

    offset = 8
    result: list[ManifestThumbnailEntry] = []
    for index in range(count):
        if offset + 4 > len(data):
            raise AuctionThumbnailManifestError(
                f"manifest ended before record {index} length"
            )
        name_length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if name_length <= 0 or name_length > _MAX_NAME_LENGTH:
            raise AuctionThumbnailManifestError(
                f"invalid logical name length at record {index}: {name_length}"
            )

        end_name = offset + name_length
        end_record = end_name + 16
        if end_record > len(data):
            raise AuctionThumbnailManifestError(
                f"manifest ended inside record {index}"
            )

        raw_name = data[offset:end_name]
        guid_bytes = data[end_name:end_record]
        offset = end_record

        try:
            logical_name = raw_name.decode("utf-8")
            guid_text = str(uuid.UUID(bytes_le=guid_bytes))
        except (UnicodeDecodeError, ValueError):
            continue

        match = _LOGICAL_NAME_RE.match(logical_name)
        if not match:
            continue

        try:
            car_id = int(match.group("car_id"))
        except ValueError:
            continue

        result.append(
            ManifestThumbnailEntry(
                index=index,
                logical_name=logical_name,
                car_id=car_id,
                guid=guid_text,
                path=cache_dir / f"{guid_text}.webp",
                instance_key=match.group("instance_key").lower(),
                livery_token=(match.group("livery_token") or "").lower(),
            )
        )

    return result


def container_download_timestamp(container_name: str) -> Optional[float]:
    """Return the UTC acquisition timestamp embedded in an FH6 container name."""
    match = _CONTAINER_TIME_RE.search(container_name or "")
    if not match:
        return None
    try:
        value = datetime.strptime(match.group("stamp"), "%Y%m%d%H%M%S")
        return value.replace(tzinfo=timezone.utc).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def crockford32_rfc_encode(raw: bytes) -> str:
    """Encode bytes with FH6's RFC-style bit grouping and Crockford alphabet."""
    output: list[str] = []
    accumulator = 0
    bit_count = 0

    for byte in raw:
        accumulator = (accumulator << 8) | byte
        bit_count += 8
        while bit_count >= 5:
            bit_count -= 5
            output.append(_CROCKFORD32[(accumulator >> bit_count) & 0x1F])
            accumulator &= (1 << bit_count) - 1 if bit_count else 0

    if bit_count:
        output.append(
            _CROCKFORD32[(accumulator << (5 - bit_count)) & 0x1F]
        )

    return "".join(output)


def _header_livery_token(record: LiveryRecord) -> str:
    """Return the verified 26-character manifest token for a livery header."""
    header_path = record.container_path / "header"
    try:
        data = header_path.read_bytes()
    except OSError:
        return ""
    if len(data) < 16:
        return ""
    token = crockford32_rfc_encode(data[-16:])
    return token if len(token) == 26 else ""


def assign_auction_thumbnails(
    records: Iterable[LiveryRecord],
    cache_dir: Path | None,
) -> AuctionThumbnailMatchStats:
    """Attach CacheThumbnails WebPs to SoulBoundLivery records deterministically.

    Verified mapping:
      SoulBound header final 16 raw bytes
        -> Crockford Base32 (RFC-style bit grouping)
        -> 26-character token after ``u`` in the manifest logical name
        -> Windows GUID from the manifest first table
        -> ``<guid>.webp`` in CacheThumbnails.

    File creation/modification times and manifest insertion order are deliberately
    not used for matching. If more than one manifest row has the same
    CarOrdinal + token, the record is treated as ambiguous instead of guessed.
    """
    auction_records = [
        record for record in records if record.kind == "SoulBoundLivery"
    ]
    for record in auction_records:
        embedded = container_download_timestamp(record.container_name)
        if embedded is not None:
            record.downloaded_at = embedded
        record.thumbnail_path = None

    if (
        not auction_records
        or cache_dir is None
        or not is_thumbnail_cache_dir(cache_dir)
    ):
        return AuctionThumbnailMatchStats(
            auction_count=len(auction_records),
            unmatched=len(auction_records),
        )

    try:
        entries = read_thumbnail_manifest(Path(cache_dir))
    except AuctionThumbnailManifestError:
        return AuctionThumbnailMatchStats(
            auction_count=len(auction_records),
            unmatched=len(auction_records),
        )

    by_identity: dict[tuple[int, str], list[ManifestThumbnailEntry]] = {}
    for entry in entries:
        if not entry.livery_token:
            continue
        by_identity.setdefault(
            (entry.car_id, entry.livery_token),
            [],
        ).append(entry)

    matched = 0
    ambiguous = 0

    for record in auction_records:
        if record.car_id is None:
            continue
        token = _header_livery_token(record)
        if not token:
            continue

        candidates = by_identity.get((int(record.car_id), token), [])
        if len(candidates) != 1:
            if len(candidates) > 1:
                ambiguous += 1
            continue

        entry = candidates[0]
        if not entry.path.is_file():
            continue

        record.thumbnail_path = entry.path
        matched += 1

    return AuctionThumbnailMatchStats(
        auction_count=len(auction_records),
        matched_by_header_id=matched,
        ambiguous=ambiguous,
        unmatched=max(0, len(auction_records) - matched),
    )
