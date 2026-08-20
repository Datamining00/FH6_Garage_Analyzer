from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


_PATCH_FLAG = "_fh6assistant_raw_transform_anomaly_diagnostic_v1"


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


def _selected_group_ids(trace_call: dict[str, Any]) -> set[str]:
    """Select anomalous groups plus immediate source-order neighbours.

    The real sample exposed a unique top-level group with flags=0xff and an
    extended livery marker. Neighbouring groups are included so the raw bytes
    that open/close a missing parent transform can be inspected without
    hard-coding a section name, shape word, car, creator, or source offset.
    """
    groups = [item for item in list(trace_call.get("groups") or ()) if isinstance(item, dict)]
    ordered = sorted(groups, key=lambda item: int(item.get("offset") or 0))
    anomaly_indexes: set[int] = set()
    for index, group in enumerate(ordered):
        flags = int(group.get("flags") or 0)
        marker = str(group.get("marker_hex") or "").lower()
        if flags == 0xFF or marker.startswith("0002000100000003"):
            anomaly_indexes.add(index)
    selected: set[str] = set()
    for index in anomaly_indexes:
        for neighbour in range(max(0, index - 3), min(len(ordered), index + 4)):
            group_id = str(ordered[neighbour].get("group_id") or "")
            if group_id:
                selected.add(group_id)
    return selected


def _group_descendant_offset_bounds(trace_call: dict[str, Any], group_id: str) -> tuple[int | None, int | None]:
    offsets: list[int] = []
    for layer in list(trace_call.get("layers") or ()):
        if not isinstance(layer, dict) or group_id not in list(layer.get("group_chain") or ()):
            continue
        try:
            offsets.append(int(layer.get("source_offset")))
        except (TypeError, ValueError):
            continue
    if not offsets:
        return None, None
    return min(offsets), max(offsets)


def _scan_livery_transform_candidates(decoder: Any, body: bytes, start: int, stop: int) -> list[dict[str, Any]]:
    end = len(body)
    start = max(0, int(start))
    stop = min(end, int(stop))
    found: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for pos in range(start, stop):
        for invert in (True, False):
            try:
                result = decoder.read_livery_transform(
                    body,
                    pos,
                    end,
                    invert_odd_rotation=invert,
                )
            except Exception:
                result = None
            if result is None:
                continue
            size, transform, marker = result
            key = (int(pos), int(size), bytes(marker).hex())
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "offset": int(pos),
                    "size": int(size),
                    "end_offset": int(pos) + int(size),
                    "marker_hex": bytes(marker).hex(),
                    "invert_odd_rotation": bool(invert),
                    "transform": _transform_dict(transform),
                }
            )
    return sorted(found, key=lambda item: (item["offset"], item["size"]))


def _scan_group_candidates(decoder: Any, body: bytes, start: int, stop: int) -> list[dict[str, Any]]:
    end = len(body)
    start = max(0, int(start))
    stop = min(end, int(stop))
    found: list[dict[str, Any]] = []
    for pos in range(start, stop):
        candidates = []
        try:
            counted = decoder.valid_counted_group_at(body, pos, end, livery=True)
        except Exception:
            counted = None
        if counted is not None:
            candidates.append(("counted", counted))
        try:
            markerless = decoder.valid_markerless_group_at(
                body,
                pos,
                end,
                allow_count_one=True,
                livery=True,
            )
        except Exception:
            markerless = None
        if markerless is not None:
            candidates.append(("markerless", markerless))
        for kind, info in candidates:
            found.append(
                {
                    "offset": int(pos),
                    "kind": kind,
                    "count": int(getattr(info, "count", 0) or 0),
                    "size": int(getattr(info, "size", 0) or 0),
                    "flags": int(getattr(info, "flags", 0) or 0),
                    "marker_hex": bytes(getattr(info, "marker", b"") or b"").hex(),
                    "inline_transform": (
                        _transform_dict(getattr(info, "inline_transform", None))
                        if getattr(info, "inline_transform", None) is not None
                        else None
                    ),
                    "inline_for_first_child": bool(getattr(info, "inline_for_first_child", False)),
                }
            )
    return found


def _raw_anomaly_report(decoder: Any, body: bytes, trace_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    end = len(body)
    for call in trace_calls:
        if not isinstance(call, dict):
            continue
        selected = _selected_group_ids(call)
        if not selected:
            continue
        groups = {
            str(group.get("group_id") or ""): group
            for group in list(call.get("groups") or ())
            if isinstance(group, dict)
        }
        for group_id in sorted(selected, key=lambda gid: int(groups[gid].get("offset") or 0)):
            group = groups[group_id]
            offset = int(group.get("offset") or 0)
            min_layer_offset, max_layer_offset = _group_descendant_offset_bounds(call, group_id)
            window_start = max(0, offset - 96)
            window_end = min(end, offset + 96)
            results.append(
                {
                    "call_index": int(call.get("call_index") or 0),
                    "section": call.get("requested_section"),
                    "group_id": group_id,
                    "group_offset": offset,
                    "group_parent": group.get("parent_group_id"),
                    "group_depth": int(group.get("depth") or 0),
                    "group_source": group.get("source"),
                    "group_flags": int(group.get("flags") or 0),
                    "group_marker_hex": group.get("marker_hex"),
                    "group_local_transform": group.get("local_transform"),
                    "descendant_min_source_offset": min_layer_offset,
                    "descendant_max_source_offset": max_layer_offset,
                    "window_start": window_start,
                    "window_end": window_end,
                    "window_hex": body[window_start:window_end].hex(),
                    "transform_candidates": _scan_livery_transform_candidates(
                        decoder,
                        body,
                        window_start,
                        min(end, offset + 32),
                    ),
                    "group_candidates": _scan_group_candidates(
                        decoder,
                        body,
                        window_start,
                        min(end, offset + 32),
                    ),
                }
            )
    return results


def install_raw_transform_anomaly_diagnostic() -> None:
    """Augment the group-transform JSON with raw parser evidence only."""
    from .livery_preview import _load_backend
    from . import livery_group_transform_diagnostic as group_diag

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original_decode_forza_source = decoder.decode_forza_source

    def decode_forza_source_with_raw_anomaly_trace(path, allow_locked: bool = False, game: str | None = "fh6"):
        decoded = original_decode_forza_source(path, allow_locked=allow_locked, game=game)
        try:
            if str(getattr(decoded, "source_kind", "")).casefold() != "clivery":
                return decoded
            source = Path(getattr(decoded, "source_path", path))
            payload = decoder.unwrap_forza_container(source)
            body, _counts, _meta = decoder.extract_livery_payload(payload)
            trace_calls = list(group_diag._trace_buffer())
            destination = group_diag._diagnostic_path(source)
            document = json.loads(destination.read_text(encoding="utf-8"))
            document["raw_transform_anomalies"] = _raw_anomaly_report(
                decoder,
                body,
                trace_calls,
            )
            document["raw_anomaly_behavior_changed"] = False
            destination.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"[FH6_RAW_TRANSFORM_TRACE] diagnostic augmentation failed: {exc}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
        return decoded

    decoder.decode_forza_source = decode_forza_source_with_raw_anomaly_trace
    setattr(decoder, _PATCH_FLAG, True)
