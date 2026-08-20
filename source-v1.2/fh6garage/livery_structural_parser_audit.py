from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


_PATCH_FLAG = "_fh6assistant_structural_parser_audit_v1"
_WARNING_PREFIX = "[FH6_STRUCTURAL_PARSE_AUDIT]"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _transform_dict(transform: Any) -> dict[str, float | None]:
    return {
        "x": _finite(getattr(transform, "x", None)),
        "y": _finite(getattr(transform, "y", None)),
        "sx": _finite(getattr(transform, "sx", None)),
        "sy": _finite(getattr(transform, "sy", None)),
        "rotation": _finite(getattr(transform, "rotation", None)),
    }


def _transform_is_plausible(transform: Any) -> bool:
    values = _transform_dict(transform)
    x = values["x"]
    y = values["y"]
    sx = values["sx"]
    sy = values["sy"]
    rotation = values["rotation"]
    if None in (x, y, sx, sy, rotation):
        return False
    return (
        abs(float(x)) < 50000.0
        and abs(float(y)) < 50000.0
        and 1e-6 < abs(float(sx)) < 200.0
        and 1e-6 < abs(float(sy)) < 200.0
        and abs(float(rotation)) <= 10000.0
    )


def _group_at(decoder: Any, data: bytes, pos: int, end: int) -> tuple[str, Any] | None:
    try:
        counted = decoder.valid_counted_group_at(data, pos, end, livery=True)
    except Exception:
        counted = None
    if counted is not None:
        return "counted_group", counted
    try:
        markerless = decoder.valid_markerless_group_at(
            data,
            pos,
            end,
            allow_count_one=True,
            livery=True,
        )
    except Exception:
        markerless = None
    if markerless is not None:
        return "markerless_group", markerless
    return None


def _successor_after_bare_transform(decoder: Any, data: bytes, pos: int, end: int) -> dict[str, Any] | None:
    """Describe a strongly structured child boundary after a bare 16-byte transform.

    This is intentionally diagnostic.  It recognizes several plausible FH6
    grammar continuations but does not assign parent ownership or mutate the
    decoder tree.  Unknown grammar is surfaced instead of silently guessed.
    """
    child_pos = int(pos) + 16
    if child_pos >= end:
        return None

    direct_group = _group_at(decoder, data, child_pos, end)
    if direct_group is not None:
        kind, info = direct_group
        return {
            "kind": "bare_before_group",
            "score": 9,
            "successor_offset": child_pos,
            "group_kind": kind,
            "group_count": int(getattr(info, "count", 0) or 0),
            "group_size": int(getattr(info, "size", 0) or 0),
            "group_flags": int(getattr(info, "flags", 0) or 0),
            "group_marker_hex": bytes(getattr(info, "marker", b"") or b"").hex(),
        }

    try:
        child_transform = decoder.read_livery_transform(
            data,
            child_pos,
            end,
            invert_odd_rotation=True,
        )
    except Exception:
        child_transform = None
    if child_transform is not None:
        size, transform, marker = child_transform
        successor_pos = child_pos + int(size)
        # read_livery_transform already proves a group successor; record the
        # concrete group when it begins exactly at the returned boundary.
        group = _group_at(decoder, data, successor_pos, end)
        return {
            "kind": "bare_before_livery_transform",
            "score": 10,
            "successor_offset": child_pos,
            "child_transform_size": int(size),
            "child_marker_hex": bytes(marker).hex(),
            "child_transform": _transform_dict(transform),
            "following_group_offset": successor_pos if group is not None else None,
            "following_group_kind": group[0] if group is not None else None,
            "following_group_count": int(getattr(group[1], "count", 0) or 0) if group is not None else None,
        }

    try:
        if decoder.is_valid_shape_at(data, child_pos, end):
            return {
                "kind": "bare_before_shape",
                "score": 8,
                "successor_offset": child_pos,
            }
        if decoder.is_livery_logo_at(data, child_pos, end):
            return {
                "kind": "bare_before_raster_logo",
                "score": 8,
                "successor_offset": child_pos,
            }
    except Exception:
        pass

    try:
        trailer = decoder.livery_transform_trailer(data, child_pos, end)
    except Exception:
        trailer = None
    if trailer is not None:
        trailer_size, trailing_sy = trailer
        group_pos = child_pos + int(trailer_size)
        group = _group_at(decoder, data, group_pos, end)
        if group is not None:
            return {
                "kind": "bare_before_trailer_group",
                "score": 8,
                "successor_offset": child_pos,
                "trailer_size": int(trailer_size),
                "trailing_sy": _finite(trailing_sy),
                "following_group_offset": group_pos,
                "following_group_kind": group[0],
                "following_group_count": int(getattr(group[1], "count", 0) or 0),
            }

    # A one-byte livery control flag can sit between a transform and a group.
    if child_pos + 1 < end and data[child_pos] in (0x01, 0x02, 0x03, 0x0F, 0xFF):
        group = _group_at(decoder, data, child_pos + 1, end)
        if group is not None:
            return {
                "kind": "bare_before_control_group",
                "score": 7,
                "successor_offset": child_pos,
                "control_byte": int(data[child_pos]),
                "following_group_offset": child_pos + 1,
                "following_group_kind": group[0],
                "following_group_count": int(getattr(group[1], "count", 0) or 0),
            }

    return None


def _already_framed_at(decoder: Any, data: bytes, pos: int, end: int) -> bool:
    """Return True when the stock decoder already has an unambiguous record here."""
    try:
        if decoder.is_valid_shape_at(data, pos, end) or decoder.is_livery_logo_at(data, pos, end):
            return True
        if _group_at(decoder, data, pos, end) is not None:
            return True
        if decoder.read_livery_transform(data, pos, end, invert_odd_rotation=True) is not None:
            return True
    except Exception:
        return True
    return False


def scan_unframed_transform_candidates(decoder: Any, body: bytes) -> list[dict[str, Any]]:
    """Scan for plausible transforms the current livery grammar could skip.

    Candidates are evidence, not fixes.  The scanner only records a transform
    when a second, independently recognizable child boundary immediately
    follows it.  This catches the class of bug that previously leaked float
    bytes into parser flags without hard-coding a car, section, phrase, or
    source offset.
    """
    end = len(body)
    results: list[dict[str, Any]] = []
    for pos in range(0, max(0, end - 32)):
        if _already_framed_at(decoder, body, pos, end):
            continue
        try:
            transform = decoder.read_transform_payload(body, pos, end)
        except Exception:
            transform = None
        if transform is None or not _transform_is_plausible(transform):
            continue
        successor = _successor_after_bare_transform(decoder, body, pos, end)
        if successor is None or int(successor.get("score") or 0) < 7:
            continue
        # Suppress obvious identity coincidences unless the structural evidence
        # is strongest.  Real omitted parents normally carry placement data.
        values = _transform_dict(transform)
        identity_like = (
            abs(float(values["x"] or 0.0)) < 1e-6
            and abs(float(values["y"] or 0.0)) < 1e-6
            and abs(float(values["sx"] or 1.0) - 1.0) < 1e-6
            and abs(float(values["sy"] or 1.0) - 1.0) < 1e-6
            and abs(float(values["rotation"] or 0.0)) < 1e-6
        )
        if identity_like and int(successor.get("score") or 0) < 10:
            continue
        window_start = max(0, pos - 32)
        window_end = min(end, pos + 64)
        results.append(
            {
                "offset": int(pos),
                "transform": values,
                "successor": successor,
                "window_start": window_start,
                "window_end": window_end,
                "window_hex": body[window_start:window_end].hex(),
            }
        )
    return results


def _section_ranges(decoded: Any) -> list[dict[str, Any]]:
    grouped: dict[str, list[int]] = {}
    for layer in list(getattr(decoded, "layers", ()) or ()):
        if not isinstance(layer, dict):
            continue
        name = str(layer.get("section") or "")
        try:
            offset = int(layer.get("source_offset"))
        except (TypeError, ValueError):
            continue
        if name:
            grouped.setdefault(name, []).append(offset)
    ranges = []
    for name, offsets in grouped.items():
        ranges.append(
            {
                "section": name,
                "min_source_offset": min(offsets),
                "max_source_offset": max(offsets),
                "layer_count": len(offsets),
            }
        )
    return sorted(ranges, key=lambda item: int(item["min_source_offset"]))


def _assign_section(candidate_offset: int, ranges: list[dict[str, Any]]) -> str | None:
    for item in ranges:
        if int(item["min_source_offset"]) - 64 <= candidate_offset <= int(item["max_source_offset"]) + 64:
            return str(item["section"])
    return None


def _diagnostic_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base) / "FH6GarageAnalyzer"
    else:
        root = Path.home() / ".fh6garage"
    target = root / "livery_parser_audits"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _diagnostic_path(source: Path) -> Path:
    import hashlib

    key = hashlib.sha1(str(source.resolve()).encode("utf-8", errors="replace")).hexdigest()[:20]
    return _diagnostic_dir() / f"{source.name}-{key}-parser-audit.json"


def install_livery_structural_parser_audit() -> None:
    """Add a non-invasive structural audit around C_livery decoding."""
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original_decode_forza_source = decoder.decode_forza_source

    def decode_forza_source_with_audit(path, allow_locked: bool = False, game: str | None = "fh6"):
        decoded = original_decode_forza_source(path, allow_locked=allow_locked, game=game)
        try:
            if str(getattr(decoded, "source_kind", "")).casefold() != "clivery":
                return decoded
            source = Path(getattr(decoded, "source_path", path))
            payload = decoder.unwrap_forza_container(source)
            body, counts, meta = decoder.extract_livery_payload(payload)
            candidates = scan_unframed_transform_candidates(decoder, body)
            ranges = _section_ranges(decoded)
            for item in candidates:
                item["section"] = _assign_section(int(item["offset"]), ranges)

            document = {
                "purpose": (
                    "Detect structurally plausible livery transforms that are not framed by the current decoder grammar. "
                    "The audit does not change decoding, layer order, transforms, masks, or rendering."
                ),
                "behavior_changed_by_audit": False,
                "source_name": source.name,
                "source_path": str(source),
                "body_size": len(body),
                "section_counts": {
                    name: int(counts[index]) if index < len(counts) else 0
                    for index, name in enumerate(getattr(decoder, "LIVERY_SECTION_NAMES", ()))
                },
                "payload_meta": meta,
                "decoded_section_ranges": ranges,
                "unframed_transform_candidate_count": len(candidates),
                "unframed_transform_candidates": candidates,
            }
            destination = _diagnostic_path(source)
            destination.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

            if candidates:
                report = dict(getattr(decoded, "report", {}) or {})
                warnings = [str(item) for item in list(report.get("warnings") or ())]
                sections = sorted({str(item.get("section")) for item in candidates if item.get("section")})
                where = ", ".join(sections) if sections else "unknown section"
                warnings.append(
                    f"{_WARNING_PREFIX} {len(candidates)} unframed transform candidate(s) remain in {where}; "
                    "rendering may be structurally ambiguous. See livery_parser_audits."
                )
                report["warnings"] = list(dict.fromkeys(warnings))
                report["structural_parse_audit"] = {
                    "candidate_count": len(candidates),
                    "sections": sections,
                    "diagnostic_path": str(destination),
                    "behavior_changed": False,
                }
                decoded.report = report
        except Exception as exc:
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"{_WARNING_PREFIX} audit failed: {exc}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
        return decoded

    decoder.decode_forza_source = decode_forza_source_with_audit
    setattr(decoder, _PATCH_FLAG, True)
