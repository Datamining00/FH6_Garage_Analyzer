from __future__ import annotations

import hashlib
import math
import struct
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


MANUFACTURER_COLORS_FORMAT = "fh6_manufacturer_colors_v1"
MANUFACTURER_COLORS_REVISION = 1
BUNDLE_TAG = 0x47727562  # "Grub"
MANUFACTURER_COLORS_BLOB_TAG = 0x4D4E434C
BLOB_INFO_SIZE = 0x18
FH6_GROUP_TRAILER_SIZE = 27
CUSTOM_COLOR_SELECTOR = 0xFFFFFFFF
_MAX_BLOB_COUNT = 4096
_MAX_STRING_BYTES = 1 << 20
_MAX_MATERIAL_NAMES = 4096


class ManufacturerColorsError(RuntimeError):
    pass


def _require(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ManufacturerColorsError(f"{label} exceeds ManufacturerColors data at 0x{offset:x}.")


def _u16(data: bytes, offset: int) -> int:
    _require(data, offset, 2, "u16")
    return int.from_bytes(data[offset : offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    _require(data, offset, 4, "u32")
    return int.from_bytes(data[offset : offset + 4], "little")


def _f32(data: bytes, offset: int) -> float:
    _require(data, offset, 4, "f32")
    value = struct.unpack_from("<f", data, offset)[0]
    if not math.isfinite(value):
        raise ManufacturerColorsError(f"Manufacturer color contains a non-finite float at 0x{offset:x}.")
    return float(value)


def _read_7bit_length(data: bytes, offset: int, limit: int) -> tuple[int, int]:
    """Read the .NET/Syroot VariableByteCount string length.

    ForzaTechStudio documents these bundle strings as .NET 7-bit encoded integer
    byte lengths. Five bytes are the maximum representation for a signed Int32;
    values outside 31 bits are rejected rather than truncated.
    """
    value = 0
    shift = 0
    pos = offset
    for index in range(5):
        if pos >= limit or pos >= len(data):
            raise ManufacturerColorsError("Manufacturer color has a truncated 7-bit string length.")
        byte = data[pos]
        pos += 1
        if index == 4 and byte > 0x07:
            raise ManufacturerColorsError("Manufacturer color 7-bit string length exceeds Int32 range.")
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            if value > _MAX_STRING_BYTES:
                raise ManufacturerColorsError(
                    f"Manufacturer color string length {value} exceeds the diagnostic safety limit."
                )
            return value, pos
        shift += 7
    raise ManufacturerColorsError("Manufacturer color 7-bit string length is malformed.")


def _read_string(data: bytes, offset: int, limit: int) -> tuple[str, int]:
    size, pos = _read_7bit_length(data, offset, limit)
    if pos + size > limit or pos + size > len(data):
        raise ManufacturerColorsError("Manufacturer color string exceeds its blob boundary.")
    raw = data[pos : pos + size]
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ManufacturerColorsError(f"Manufacturer color string is not valid UTF-8: {exc}") from exc
    return value, pos + size


def _read_color(data: bytes, offset: int, limit: int) -> tuple[list[float], int]:
    if offset + 12 > limit:
        raise ManufacturerColorsError("Manufacturer color RGB vector exceeds its blob boundary.")
    return [_f32(data, offset), _f32(data, offset + 4), _f32(data, offset + 8)], offset + 12


def _trailing_summary(data: bytes) -> dict[str, Any]:
    return {
        "size": len(data),
        "hex": data[:128].hex(),
        "hex_truncated": len(data) > 128,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _manufacturer_blob(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """Return the unique ManufacturerColors blob using the pinned FTS bundle framing."""
    if len(raw) < 16 or _u32(raw, 0) != BUNDLE_TAG:
        raise ManufacturerColorsError("ManufacturerColors.bin is not a ForzaTech Grub bundle.")

    version_major = int(raw[4])
    version_minor = int(raw[5])
    if version_major > 1 or (version_major == 1 and version_minor >= 1):
        _require(raw, 0, 20, "bundle header")
        header_size = _u32(raw, 8)
        total_size = _u32(raw, 12)
        blob_count = _u32(raw, 16)
        headers_start = 20
    else:
        header_size = _u32(raw, 8)
        total_size = _u32(raw, 12)
        blob_count = _u16(raw, 6)
        headers_start = 16

    if blob_count > _MAX_BLOB_COUNT:
        raise ManufacturerColorsError(f"Bundle blob count {blob_count} exceeds the diagnostic safety limit.")
    _require(raw, headers_start, blob_count * BLOB_INFO_SIZE, "bundle blob headers")

    candidates: list[dict[str, int]] = []
    for index in range(blob_count):
        pos = headers_start + index * BLOB_INFO_SIZE
        tag = _u32(raw, pos)
        if tag != MANUFACTURER_COLORS_BLOB_TAG:
            continue
        version_major_blob = int(raw[pos + 4])
        version_minor_blob = int(raw[pos + 5])
        metadata_count = _u16(raw, pos + 6)
        metadata_offset = _u32(raw, pos + 8)
        data_offset = _u32(raw, pos + 12)
        compressed_size = _u32(raw, pos + 16)
        uncompressed_size = _u32(raw, pos + 20)
        size_to_read = uncompressed_size if uncompressed_size > 0 else compressed_size
        if size_to_read <= 0:
            raise ManufacturerColorsError("ManufacturerColors blob advertises an empty payload.")
        _require(raw, data_offset, size_to_read, "ManufacturerColors blob payload")
        candidates.append(
            {
                "index": index,
                "version_major": version_major_blob,
                "version_minor": version_minor_blob,
                "metadata_count": metadata_count,
                "metadata_offset": metadata_offset,
                "data_offset": data_offset,
                "compressed_size": compressed_size,
                "uncompressed_size": uncompressed_size,
                "size_to_read": size_to_read,
            }
        )

    if not candidates:
        raise ManufacturerColorsError("Bundle has no ManufacturerColors blob (0x4D4E434C).")
    if len(candidates) != 1:
        raise ManufacturerColorsError(
            f"Bundle has {len(candidates)} ManufacturerColors blobs; exact palette source is ambiguous."
        )

    info = candidates[0]
    start = int(info["data_offset"])
    end = start + int(info["size_to_read"])
    metadata: dict[str, Any] = {
        "bundle_version": [version_major, version_minor],
        "bundle_header_size": header_size,
        "bundle_total_size": total_size,
        "bundle_blob_count": blob_count,
        "blob_index": info["index"],
        "blob_version": [info["version_major"], info["version_minor"]],
        "blob_metadata_count": info["metadata_count"],
        "blob_metadata_offset": info["metadata_offset"],
        "blob_data_offset": info["data_offset"],
        "blob_compressed_size": info["compressed_size"],
        "blob_uncompressed_size": info["uncompressed_size"],
        "blob_payload_size": info["size_to_read"],
    }
    return raw[start:end], metadata


def parse_manufacturer_colors_bundle(raw: bytes) -> dict[str, Any]:
    """Parse FH6 ManufacturerColors.bin without applying any paint rendering.

    The parser mirrors pinned ForzaTechStudio Bundle/BundleBlob and
    ManufacturerColorsBlob v2 framing. It preserves every group and entry rather
    than collapsing one selector to one guessed RGB value.
    """
    blob, metadata = _manufacturer_blob(raw)
    blob_version = metadata["blob_version"]
    if int(blob_version[0]) < 2:
        raise ManufacturerColorsError(
            f"ManufacturerColors blob version {blob_version[0]}.{blob_version[1]} is not the FH6 v2 contract."
        )

    pos = 0
    limit = len(blob)
    if limit < 1:
        raise ManufacturerColorsError("ManufacturerColors v2 blob is empty.")
    group_count = int(blob[pos])
    pos += 1
    groups: list[dict[str, Any]] = []

    for group_index in range(group_count):
        if pos >= limit:
            raise ManufacturerColorsError(f"Manufacturer color group {group_index} is truncated before entry count.")
        entry_count = int(blob[pos])
        pos += 1
        entries: list[dict[str, Any]] = []
        for entry_index in range(entry_count):
            if pos + 4 > limit:
                raise ManufacturerColorsError(
                    f"Manufacturer color group {group_index} entry {entry_index} is truncated before material-name count."
                )
            material_name_count = _u32(blob, pos)
            pos += 4
            if material_name_count > _MAX_MATERIAL_NAMES:
                raise ManufacturerColorsError(
                    f"Manufacturer color material-name count {material_name_count} exceeds the diagnostic safety limit."
                )
            material_names: list[str] = []
            for _ in range(material_name_count):
                value, pos = _read_string(blob, pos, limit)
                material_names.append(value)
            preview_color, pos = _read_color(blob, pos, limit)
            path, pos = _read_string(blob, pos, limit)
            entries.append(
                {
                    "index": entry_index,
                    "material_names": material_names,
                    "preview_color": preview_color,
                    "path": path,
                }
            )

        if pos + FH6_GROUP_TRAILER_SIZE > limit:
            raise ManufacturerColorsError(
                f"Manufacturer color group {group_index} has no complete 27-byte FH6 preview trailer."
            )
        primary_present = int(blob[pos])
        pos += 1
        primary_color, pos = _read_color(blob, pos, limit)
        group_preview_zero = int(blob[pos])
        pos += 1
        secondary_present = int(blob[pos])
        pos += 1
        secondary_color, pos = _read_color(blob, pos, limit)
        groups.append(
            {
                "index": group_index,
                "entry_count": entry_count,
                "entries": entries,
                "primary_group_preview_present_raw": primary_present,
                "primary_group_preview_present": bool(primary_present),
                "primary_group_preview_color": primary_color,
                "group_preview_zero_raw": group_preview_zero,
                "secondary_group_preview_present_raw": secondary_present,
                "secondary_group_preview_present": bool(secondary_present),
                "secondary_group_preview_color": secondary_color,
            }
        )

    trailing = blob[pos:]
    return {
        "format": MANUFACTURER_COLORS_FORMAT,
        "status": "manufacturer_colors_parsed",
        "source_contract": "forzatechstudio_4f373c5_manufacturercolorsblob_v2",
        "rendering_applied": False,
        "game_data_modified": False,
        **metadata,
        "group_count": group_count,
        "groups": groups,
        "blob_trailing": _trailing_summary(trailing),
        "interpretation_boundary": (
            "Paint P3A preserves the FH6 manufacturer palette structure and selector-to-group indexing only. "
            "Material-specific entry selection, UV4 swatch overlays, secondary/two-tone application, and finish "
            "shader semantics are not rendered at this stage."
        ),
    }


def resolve_manufacturer_selector(report: Any, selector: Any) -> dict[str, Any]:
    """Resolve the C_livery selector to one palette group without choosing an entry."""
    try:
        value = int(selector)
    except (TypeError, ValueError):
        return {"status": "manufacturer_selector_invalid", "selector": selector, "group": None}
    if value < 0 or value > 0xFFFFFFFF:
        return {"status": "manufacturer_selector_invalid", "selector": value, "group": None}
    if value == CUSTOM_COLOR_SELECTOR:
        return {"status": "custom_color_selector", "selector": value, "group": None}
    if not isinstance(report, dict) or report.get("status") != "manufacturer_colors_parsed":
        return {"status": "manufacturer_palette_unavailable", "selector": value, "group": None}
    groups = report.get("groups") or []
    if value >= len(groups):
        return {"status": "manufacturer_selector_out_of_range", "selector": value, "group": None}
    group = groups[value]
    if not isinstance(group, dict) or not (group.get("entries") or []):
        return {"status": "manufacturer_selector_empty_group", "selector": value, "group": group}
    return {"status": "manufacturer_group_resolved", "selector": value, "group": group}


def diagnose_manufacturer_colors_archive(archive: str | Path) -> dict[str, Any]:
    """Locate and parse the unique ManufacturerColors.bin inside a read-only car ZIP."""
    archive_path = Path(archive)
    if not archive_path.is_file():
        raise ManufacturerColorsError("Vehicle archive does not exist.")
    try:
        with zipfile.ZipFile(archive_path) as bundle:
            matches = [
                name
                for name in bundle.namelist()
                if PurePosixPath(name.replace("\\", "/")).name.casefold() == "manufacturercolors.bin"
            ]
            if not matches:
                return {
                    "format": MANUFACTURER_COLORS_FORMAT,
                    "status": "manufacturer_colors_not_present",
                    "rendering_applied": False,
                    "game_data_modified": False,
                    "archive_file": str(archive_path),
                    "groups": [],
                    "issues": [],
                }
            if len(matches) != 1:
                return {
                    "format": MANUFACTURER_COLORS_FORMAT,
                    "status": "manufacturer_colors_archive_member_ambiguous",
                    "rendering_applied": False,
                    "game_data_modified": False,
                    "archive_file": str(archive_path),
                    "candidate_entries": sorted(matches),
                    "groups": [],
                    "issues": [
                        f"Vehicle archive contains {len(matches)} files named ManufacturerColors.bin; source is ambiguous."
                    ],
                }
            member = matches[0]
            raw = bundle.read(member)
    except zipfile.BadZipFile as exc:
        raise ManufacturerColorsError(f"Vehicle archive is not a readable ZIP: {exc}") from exc
    except OSError as exc:
        raise ManufacturerColorsError(f"Could not read vehicle archive: {exc}") from exc

    report = parse_manufacturer_colors_bundle(raw)
    report = dict(report)
    report.update(
        {
            "archive_file": str(archive_path),
            "archive_entry": member,
            "source_size": len(raw),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "game_data_modified": False,
        }
    )
    return report
