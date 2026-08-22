from __future__ import annotations

import os
import re
import struct
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import LiveryRecord


_MANIFEST_VERSION = 2
_MAX_RECORDS = 1_000_000
_MAX_NAME_LENGTH = 4096
_LOGICAL_NAME_RE = re.compile(
    r"^(?P<car_id>\d+)_.*_bigThumb\.webp$",
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


@dataclass(frozen=True, slots=True)
class AuctionThumbnailMatchStats:
    auction_count: int = 0
    matched_by_time: int = 0
    matched_by_order: int = 0
    unmatched: int = 0

    @property
    def matched(self) -> int:
        return self.matched_by_time + self.matched_by_order


def is_thumbnail_cache_dir(path: Path | str | None) -> bool:
    if path is None:
        return False
    try:
        candidate = Path(path).expanduser()
    except (TypeError, ValueError):
        return False
    return candidate.is_dir() and (candidate / ".manifest").is_file()


def auto_detect_thumbnail_cache(local_appdata: Path | None = None) -> Optional[Path]:
    """Locate a verified FH6 CacheThumbnails directory.

    Xbox/Microsoft Store installations are detected by the ForteBaseGame package
    prefix rather than a hard-coded publisher suffix.  A Steam-style LocalAppData
    location is also checked, but it is accepted only when a real .manifest is
    present, so an unverified/empty candidate cannot be selected accidentally.
    """
    if local_appdata is None:
        raw = os.environ.get("LOCALAPPDATA", "").strip()
        if not raw:
            return None
        local_appdata = Path(raw)

    local_appdata = Path(local_appdata)
    candidates: list[Path] = []

    packages = local_appdata / "Packages"
    if packages.is_dir():
        for package in sorted(packages.glob("Microsoft.ForteBaseGame_*")):
            candidates.append(
                package
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )

    # Steam candidate.  The exact Steam CacheThumbnails layout is accepted only
    # if the manifest exists on the user's machine.
    candidates.append(
        local_appdata
        / "ForzaHorizon6"
        / "LocalStorage_Cache"
        / "CacheThumbnails"
    )

    for candidate in candidates:
        if is_thumbnail_cache_dir(candidate):
            return candidate
    return None


def read_thumbnail_manifest(cache_dir: Path) -> list[ManifestThumbnailEntry]:
    """Read only the verified first table of CacheThumbnails/.manifest.

    Verified layout (manifest v2):
      uint32 version
      uint32 record_count
      repeated record_count times:
        uint32 logical_name_length
        logical_name bytes (UTF-8/ASCII)
        16-byte Windows GUID (little-endian GUID field layout)

    The manifest contains additional tables after this block.  They are
    deliberately ignored until their semantics are independently verified.
    """
    cache_dir = Path(cache_dir)
    manifest_path = cache_dir / ".manifest"
    try:
        data = manifest_path.read_bytes()
    except OSError as exc:
        raise AuctionThumbnailManifestError(str(exc)) from exc

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
        try:
            logical_name = data[offset:end_name].decode("utf-8")
        except UnicodeDecodeError:
            logical_name = ""
        guid_bytes = data[end_name:end_record]
        offset = end_record

        match = _LOGICAL_NAME_RE.match(logical_name)
        if not match:
            continue
        try:
            car_id = int(match.group("car_id"))
            guid_text = str(uuid.UUID(bytes_le=guid_bytes))
        except (ValueError, AttributeError):
            continue

        result.append(
            ManifestThumbnailEntry(
                index=index,
                logical_name=logical_name,
                car_id=car_id,
                guid=guid_text,
                path=cache_dir / f"{guid_text}.webp",
            )
        )

    return result


def container_download_timestamp(container_name: str) -> Optional[float]:
    """Return the UTC timestamp encoded in an FH6 container name."""
    match = _CONTAINER_TIME_RE.search(container_name or "")
    if not match:
        return None
    try:
        value = datetime.strptime(match.group("stamp"), "%Y%m%d%H%M%S")
        return value.replace(tzinfo=timezone.utc).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _filesystem_created_timestamp(path: Path) -> Optional[float]:
    try:
        stat = path.stat()
    except OSError:
        return None
    value = getattr(stat, "st_birthtime", stat.st_ctime)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_time_batch(entries: Iterable[ManifestThumbnailEntry]) -> bool:
    times = [
        value
        for entry in entries
        if (value := _filesystem_created_timestamp(entry.path)) is not None
    ]
    if len(times) < 2:
        return True
    # Reinstall/copy batches commonly collapse creation timestamps to the same
    # instant.  In that case time proximity contains no discriminating signal.
    return max(times) - min(times) <= 2.0


def assign_auction_thumbnails(
    records: Iterable[LiveryRecord],
    cache_dir: Path | None,
    *,
    proximity_seconds: float = 90.0,
) -> AuctionThumbnailMatchStats:
    """Attach cached WebP paths to SoulBoundLivery records.

    Matching uses two independently observable signals:
      1. Normal installs: embedded SoulBound acquisition time vs WebP creation
         time, constrained to the same CarOrdinal.
      2. Reinstall/copy batches where file creation times collapse: manifest
         insertion order vs the immutable timestamp embedded in the container
         name, again constrained to the same CarOrdinal.

    The second rule is a deterministic fallback verified against the supplied
    three-auction sample.  It intentionally does not pretend that the currently
    unexplained logical-name token is derived from the SoulBound header.
    """
    auction_records = [r for r in records if r.kind == "SoulBoundLivery"]
    for record in auction_records:
        embedded = container_download_timestamp(record.container_name)
        if embedded is not None:
            record.downloaded_at = embedded
        record.thumbnail_path = None

    if not auction_records or cache_dir is None or not is_thumbnail_cache_dir(cache_dir):
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

    records_by_car: dict[int, list[LiveryRecord]] = defaultdict(list)
    entries_by_car: dict[int, list[ManifestThumbnailEntry]] = defaultdict(list)
    for record in auction_records:
        if record.car_id is not None:
            records_by_car[int(record.car_id)].append(record)
    for entry in entries:
        entries_by_car[entry.car_id].append(entry)

    matched_time = 0
    matched_order = 0

    for car_id, car_records in records_by_car.items():
        car_entries = sorted(entries_by_car.get(car_id, []), key=lambda e: e.index)
        if not car_entries:
            continue

        car_records = sorted(
            car_records,
            key=lambda r: (
                container_download_timestamp(r.container_name) is None,
                container_download_timestamp(r.container_name) or 0.0,
                r.container_name,
            ),
        )

        if _same_time_batch(car_entries):
            # Creation time is unusable (typical after a reinstall/copy).  Pair
            # the newest N manifest insertions with the N SoulBound containers
            # in their immutable acquisition order.  Missing WebPs do not shift
            # the pairing; the record simply remains without a thumbnail.
            count = min(len(car_records), len(car_entries))
            if count:
                selected_records = car_records[-count:]
                selected_entries = car_entries[-count:]
                for record, entry in zip(selected_records, selected_entries):
                    if entry.path.is_file():
                        record.thumbnail_path = entry.path
                        matched_order += 1
            continue

        # Normal case: use unique nearest creation times within a conservative
        # window.  This avoids selecting a visually wrong thumbnail merely
        # because it shares a CarOrdinal.
        remaining_entries = set(range(len(car_entries)))
        for record in car_records:
            stamp = container_download_timestamp(record.container_name)
            if stamp is None:
                continue
            best: tuple[float, int] | None = None
            for entry_index in remaining_entries:
                entry = car_entries[entry_index]
                created = _filesystem_created_timestamp(entry.path)
                if created is None:
                    continue
                distance = abs(created - stamp)
                if distance > proximity_seconds:
                    continue
                if best is None or distance < best[0]:
                    best = (distance, entry_index)
            if best is None:
                continue
            _, entry_index = best
            entry = car_entries[entry_index]
            remaining_entries.remove(entry_index)
            if entry.path.is_file():
                record.thumbnail_path = entry.path
                matched_time += 1

    matched_total = matched_time + matched_order
    return AuctionThumbnailMatchStats(
        auction_count=len(auction_records),
        matched_by_time=matched_time,
        matched_by_order=matched_order,
        unmatched=max(0, len(auction_records) - matched_total),
    )
