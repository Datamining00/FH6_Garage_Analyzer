from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path
from typing import Any, Iterable


_PATCH_FLAG = "_fh6assistant_structural_parser_audit_v2"
_WARNING_PREFIX = "[FH6_STRUCTURAL_PARSE_AUDIT]"
_TRACE_LOCAL = threading.local()


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
    """Describe a strongly structured child boundary after a bare transform."""
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
        group = _group_at(decoder, data, successor_pos, end)
        group_offset = successor_pos if group is not None else None

        # read_livery_transform can prove a group one control byte after the
        # returned transform span. Preserve that exact location in diagnostics.
        if group is None and successor_pos + 1 < end:
            shifted = _group_at(decoder, data, successor_pos + 1, end)
            if shifted is not None:
                group = shifted
                group_offset = successor_pos + 1

        return {
            "kind": "bare_before_livery_transform",
            "score": 10,
            "successor_offset": child_pos,
            "child_transform_size": int(size),
            "child_marker_hex": bytes(marker).hex(),
            "child_transform": _transform_dict(transform),
            "following_group_offset": group_offset,
            "following_group_kind": group[0] if group is not None else None,
            "following_group_count": int(getattr(group[1], "count", 0) or 0) if group is not None else None,
        }

    try:
        if decoder.is_valid_shape_at(data, child_pos, end):
            return {"kind": "bare_before_shape", "score": 8, "successor_offset": child_pos}
        if decoder.is_livery_logo_at(data, child_pos, end):
            return {"kind": "bare_before_raster_logo", "score": 8, "successor_offset": child_pos}
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


def scan_unframed_transform_candidates(
    decoder: Any,
    body: bytes,
    candidate_offsets: Iterable[int] | None = None,
    section_by_offset: dict[int, str | None] | None = None,
) -> list[dict[str, Any]]:
    """Return plausible transforms at parser boundaries that remain unframed.

    With ``candidate_offsets=None`` the function performs the old exhaustive
    scan used by synthetic tests. Runtime audit calls pass only positions that
    the *actual patched parser* advanced through one byte at a time. This avoids
    mistaking float/color bytes inside valid shapes and group records for new
    grammar while still catching the exact failure mode where a real transform
    is silently walked byte-by-byte.
    """
    end = len(body)
    if candidate_offsets is None:
        positions: Iterable[int] = range(0, max(0, end - 32))
    else:
        positions = sorted({int(value) for value in candidate_offsets if 0 <= int(value) <= end - 32})

    results: list[dict[str, Any]] = []
    for pos in positions:
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
        item = {
            "offset": int(pos),
            "transform": values,
            "successor": successor,
            "window_start": window_start,
            "window_end": window_end,
            "window_hex": body[window_start:window_end].hex(),
        }
        if section_by_offset is not None:
            item["section"] = section_by_offset.get(int(pos))
        results.append(item)
    return results


def _section_ranges(decoded: Any) -> list[dict[str, Any]]:
    grouped: dict[str, list[int]] = {}
    for layer in list(getattr(decoded, "layers", ()) or ()):
        if not isinstance(layer, dict):
            continue
        # FH6 Assistant preserves original section provenance as source_section.
        name = str(layer.get("source_section") or layer.get("section") or "")
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


def _section_from_state(state: Any) -> str | None:
    try:
        for node in reversed(list(getattr(state, "stack", ()) or ())):
            value = getattr(node, "section", None)
            if value:
                return str(value)
    except Exception:
        return None
    return None


def _pending_snapshot(state: Any) -> dict[str, Any]:
    try:
        marker = bytes(getattr(state, "pending_marker", b"") or b"").hex()
    except Exception:
        marker = ""
    try:
        prefix = bytes(getattr(state, "pending_prefix", b"") or b"").hex()
    except Exception:
        prefix = ""
    return {
        "has_pending_transform": getattr(state, "pending_transform", None) is not None,
        "pending_marker_hex": marker,
        "pending_prefix_hex": prefix,
        "pending_flags": int(getattr(state, "pending_flags", 0) or 0),
        "pending_mask": bool(getattr(state, "pending_mask", False)),
    }


def unresolved_walk_offsets(events: list[dict[str, Any]], body_size: int) -> tuple[list[int], dict[int, str | None], dict[str, int]]:
    """Return offsets that every observed parser pass consumed as one byte."""
    relevant = [event for event in events if int(event.get("end", -1)) == int(body_size)]
    by_pos: dict[int, list[dict[str, Any]]] = {}
    for event in relevant:
        by_pos.setdefault(int(event["pos"]), []).append(event)

    unresolved: list[int] = []
    sections: dict[int, str | None] = {}
    recognized_multi_byte = 0
    for pos, items in by_pos.items():
        spans = [int(item["next_pos"]) - int(item["pos"]) for item in items]
        if any(span > 1 for span in spans):
            recognized_multi_byte += 1
            continue
        if spans and all(span == 1 for span in spans):
            unresolved.append(pos)
            sections[pos] = next((str(item["section"]) for item in items if item.get("section")), None)

    summary = {
        "walk_event_count": len(relevant),
        "unique_walk_offsets": len(by_pos),
        "single_byte_only_offsets": len(unresolved),
        "recognized_multi_byte_offsets": recognized_multi_byte,
    }
    return sorted(unresolved), sections, summary


def _diagnostic_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / "FH6GarageAnalyzer" if base else Path.home() / ".fh6garage"
    target = root / "livery_parser_audits"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _diagnostic_path(source: Path) -> Path:
    import hashlib

    key = hashlib.sha1(str(source.resolve()).encode("utf-8", errors="replace")).hexdigest()[:20]
    return _diagnostic_dir() / f"{source.name}-{key}-parser-audit.json"


def install_livery_structural_parser_audit() -> None:
    """Add a non-invasive structural audit around actual C_livery parser walks."""
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original_walk_step = decoder.walk_step

    def walk_step_with_trace(
        data,
        pos,
        end,
        state,
        livery: bool = False,
        game: str | None = None,
        livery_invert_odd_rotation: bool = True,
    ):
        before = _pending_snapshot(state) if livery else None
        section = _section_from_state(state) if livery else None
        next_pos = original_walk_step(
            data,
            pos,
            end,
            state,
            livery=livery,
            game=game,
            livery_invert_odd_rotation=livery_invert_odd_rotation,
        )
        events = getattr(_TRACE_LOCAL, "events", None)
        if events is not None and livery:
            events.append(
                {
                    "pos": int(pos),
                    "next_pos": int(next_pos),
                    "end": int(end),
                    "section": section or _section_from_state(state),
                    "before": before,
                    "after": _pending_snapshot(state),
                }
            )
        return next_pos

    decoder.walk_step = walk_step_with_trace
    original_decode_forza_source = decoder.decode_forza_source

    def decode_forza_source_with_audit(path, allow_locked: bool = False, game: str | None = "fh6"):
        previous_events = getattr(_TRACE_LOCAL, "events", None)
        events: list[dict[str, Any]] = []
        _TRACE_LOCAL.events = events
        try:
            decoded = original_decode_forza_source(path, allow_locked=allow_locked, game=game)
        finally:
            if previous_events is None:
                try:
                    delattr(_TRACE_LOCAL, "events")
                except AttributeError:
                    pass
            else:
                _TRACE_LOCAL.events = previous_events

        try:
            if str(getattr(decoded, "source_kind", "")).casefold() != "clivery":
                return decoded
            source = Path(getattr(decoded, "source_path", path))
            payload = decoder.unwrap_forza_container(source)
            body, counts, meta = decoder.extract_livery_payload(payload)
            ranges = _section_ranges(decoded)
            single_offsets, section_by_offset, walk_summary = unresolved_walk_offsets(events, len(body))
            candidates = scan_unframed_transform_candidates(
                decoder,
                body,
                candidate_offsets=single_offsets,
                section_by_offset=section_by_offset,
            )
            for item in candidates:
                if not item.get("section"):
                    item["section"] = _assign_section(int(item["offset"]), ranges)

            document = {
                "purpose": (
                    "Detect structurally plausible livery transforms that the actual patched decoder still walks one byte at a time. "
                    "The audit does not change decoding, layer order, transforms, masks, or rendering."
                ),
                "audit_version": 2,
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
                "parser_walk_summary": walk_summary,
                "unframed_transform_candidate_count": len(candidates),
                "unframed_transform_candidates": candidates,
            }
            destination = _diagnostic_path(source)
            destination.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

            report = dict(getattr(decoded, "report", {}) or {})
            if candidates:
                warnings = [str(item) for item in list(report.get("warnings") or ())]
                sections = sorted({str(item.get("section")) for item in candidates if item.get("section")})
                where = ", ".join(sections) if sections else "unknown section"
                warnings.append(
                    f"{_WARNING_PREFIX} {len(candidates)} unresolved transform candidate(s) remain in {where}; "
                    "rendering may be structurally ambiguous. See livery_parser_audits."
                )
                report["warnings"] = list(dict.fromkeys(warnings))
                report["structural_parse_audit"] = {
                    "audit_version": 2,
                    "candidate_count": len(candidates),
                    "sections": sections,
                    "diagnostic_path": str(destination),
                    "behavior_changed": False,
                }
            else:
                report["structural_parse_audit"] = {
                    "audit_version": 2,
                    "candidate_count": 0,
                    "sections": [],
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
