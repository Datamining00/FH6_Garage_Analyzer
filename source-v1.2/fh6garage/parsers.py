from __future__ import annotations

import base64
import json
import re
import struct
import uuid
from pathlib import Path
from typing import Any, Optional

from .models import HeaderInfo, SaveMetadata


class ParseError(ValueError):
    pass


_LIVERY_KINDS = {"Livery", "BaseLivery", "SoulBoundLivery"}
_LIVERY_SECTION_MARKER = b"\x01\x02"


def _u16(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        raise ParseError("unexpected end of header")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise ParseError("unexpected end of header")
    return struct.unpack_from("<I", data, offset)[0]


def _read_utf16_string(data: bytes, offset: int) -> tuple[str, int]:
    length = _u32(data, offset)
    offset += 4
    if length > 4096:
        raise ParseError(f"unreasonable UTF-16 string length: {length}")
    end = offset + length * 2
    if end > len(data):
        raise ParseError("UTF-16 string exceeds header size")
    text = data[offset:end].decode("utf-16le", errors="replace")
    return text, end


def _uuid_text(raw: bytes) -> str:
    if len(raw) != 16:
        return ""
    try:
        return str(uuid.UUID(bytes=raw))
    except ValueError:
        return ""


def parse_forza_header(data: bytes, kind: str) -> HeaderInfo:
    """Parse FH6 livery/tuning header fields without breaking legacy identities.

    The title/description/date/creator preamble is common to the sampled v7
    headers. Livery/BaseLivery/SoulBoundLivery additionally expose a verified
    creator-relative section identified by the 0x01 0x02 marker. When that
    structural marker is absent, the historical tail-based parser remains the
    compatibility fallback (notably for older/synthetic fixtures).

    ``guid``, ``decal_count`` and ``platform_code`` deliberately retain their
    historical values because existing local annotations/history/backups may
    already depend on them. Verified creator-relative values are exposed
    separately as ``asset_guid`` and ``type_value``.
    """
    if len(data) < 48:
        raise ParseError("header is too small")

    version = _u32(data, 0)
    offset = 4
    name, offset = _read_utf16_string(data, offset)
    description, offset = _read_utf16_string(data, offset)

    # Verified against current v7 BaseLivery/Livery/SoulBoundLivery/Tuning
    # samples: uint16 year, uint32 month, uint16 day/hour/min/sec/ms.
    if offset + 28 > len(data):
        raise ParseError("header ends before common metadata")
    year = _u16(data, offset)
    month = _u32(data, offset + 2)
    day = _u16(data, offset + 6)
    hour = _u16(data, offset + 8)
    minute = _u16(data, offset + 10)
    second = _u16(data, offset + 12)
    millisecond = _u16(data, offset + 14)

    # Bytes offset+20:offset+28 form an 8-byte creator-identity block in the
    # sampled headers. Its internal semantics are not assigned yet. Keep the
    # historical +26 value for backwards compatibility only.
    _creator_identity = data[offset + 20:offset + 28]
    platform_code = _u16(data, offset + 26)

    creator_len_offset = offset + 28
    creator, creator_end = _read_utf16_string(data, creator_len_offset)

    created = ""
    if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
        created = (
            f"{year:04d}-{month:02d}-{day:02d} "
            f"{hour:02d}:{minute:02d}:{second:02d}.{millisecond:03d}"
        )

    # Historical tail values are intentionally preserved as compatibility
    # identities. In real livery samples the final 16 bytes are not the Asset
    # GUID, but existing annotations/history/backups may already key on them.
    car_id = _u32(data, len(data) - 20) if len(data) >= 20 else None
    guid = _uuid_text(data[-16:] if len(data) >= 16 else b"")

    decal_count: Optional[int] = None
    if kind in _LIVERY_KINDS and len(data) >= 24:
        decal_count = _u32(data, len(data) - 24)

    asset_guid = ""
    type_value: Optional[int] = None

    # Verified livery section, relative to the end of the creator string:
    # +0x1C marker 01 02
    # +0x25 u32 type_value (exact semantic meaning still unconfirmed)
    # +0x29 u32 target CarOrdinal
    # +0x2D byte[16] Asset GUID
    # Tuning is intentionally excluded until its distinct tail is independently
    # verified. The marker check also keeps older/synthetic headers compatible.
    livery_section_end = creator_end + 0x3D
    if (
        kind in _LIVERY_KINDS
        and livery_section_end <= len(data)
        and data[creator_end + 0x1C:creator_end + 0x1E]
        == _LIVERY_SECTION_MARKER
    ):
        type_value = _u32(data, creator_end + 0x25)
        car_id = _u32(data, creator_end + 0x29)
        asset_guid = _uuid_text(data[creator_end + 0x2D:creator_end + 0x3D])

    return HeaderInfo(
        version=version,
        name=name,
        description=description,
        creator=creator,
        created=created,
        car_id=car_id,
        guid=guid,
        decal_count=decal_count,
        platform_code=platform_code,
        asset_guid=asset_guid,
        type_value=type_value,
    )


def read_header_file(path: Path, kind: str) -> HeaderInfo:
    with path.open("rb") as fh:
        return parse_forza_header(fh.read(), kind)


def _safe_load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _decode_b64_text(value: str) -> str:
    try:
        return base64.b64decode(value, validate=True).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _first_line_value(text: str, keys: tuple[str, ...]) -> str:
    for line in text.splitlines():
        lowered = line.lower()
        if any(key.lower() in lowered for key in keys):
            if ":" in line:
                return line.split(":", 1)[1].strip()
            return line.strip()
    return ""


def parse_save_metadata(selected_path: Path, save_root: Path, containers_root: Path, active_version: str) -> SaveMetadata:
    meta = SaveMetadata(
        selected_path=selected_path,
        save_root=save_root,
        containers_root=containers_root,
        active_version=active_version,
    )

    # Version manifest: prefer <active_version>.json; otherwise inspect JSONs.
    manifest_candidates: list[Path] = []
    if active_version.isdigit():
        manifest_candidates.append(save_root / f"{active_version}.json")
    manifest_candidates.extend(sorted(save_root.glob("*.json")))

    seen: set[Path] = set()
    for path in manifest_candidates:
        if path in seen:
            continue
        seen.add(path)
        obj = _safe_load_json(path)
        if not obj or not isinstance(obj.get("Manifest"), dict):
            continue
        manifest = obj["Manifest"]
        meta.user_id = str(manifest.get("UserId", ""))
        meta.game_id = str(manifest.get("GameId", ""))
        meta.device_id = str(manifest.get("DeviceId", ""))
        meta.created = str(manifest.get("Created", ""))
        meta.last_write = str(manifest.get("LastWrite", ""))
        if not meta.active_version or meta.active_version.lower() == "current":
            meta.active_version = str(manifest.get("Version", ""))
        break

    # Context JSON carries SaveDescription and package/session metadata.
    for path in sorted(save_root.glob("*.json")):
        obj = _safe_load_json(path)
        if not obj or not isinstance(obj.get("Context"), dict):
            continue
        context = obj["Context"]
        encoded = str(context.get("SaveDescription", ""))
        meta.save_description = _decode_b64_text(encoded) if encoded else ""
        meta.package_full_name = str(context.get("PackageFullName", ""))
        meta.session_id = str(context.get("SessionId", ""))
        if not meta.active_version:
            meta.active_version = str(context.get("UploadVersion", ""))
        break

    text = meta.save_description
    if text:
        # Korean FH6 SaveDescription verified in the supplied save. English
        # fallbacks are included without making assumptions about localization.
        car_patterns = (
            r"차고\s*내\s*자동차\s*:\s*([0-9,]+)",
            r"(?:garage|cars?)\D{0,20}([0-9,]+)",
        )
        for pattern in car_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                try:
                    meta.reported_car_count = int(match.group(1).replace(",", ""))
                except ValueError:
                    pass
                break
        meta.play_time = _first_line_value(text, ("운전한 시간", "time driven", "play time"))
        meta.experience = _first_line_value(text, ("경험치", "experience", "xp"))

    return meta
