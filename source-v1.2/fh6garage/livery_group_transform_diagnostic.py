from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_PATCH_FLAG = "_fh6assistant_group_transform_diagnostic_v1"
_STATE = threading.local()


def _trace_buffer() -> list[dict[str, Any]]:
    value = getattr(_STATE, "trace_calls", None)
    if value is None:
        value = []
        _STATE.trace_calls = value
    return value


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


def _shape_transform_dict(shape: Any) -> dict[str, float | None]:
    return {
        "x": _finite(getattr(shape, "x", None)),
        "y": _finite(getattr(shape, "y", None)),
        "sx": _finite(getattr(shape, "sx", None)),
        "sy": _finite(getattr(shape, "sy", None)),
        "rotation": _finite(getattr(shape, "rotation", None)),
        "skew": _finite(getattr(shape, "skew", None)),
    }


def _decomposed_dict(decoder: Any, matrix: Any) -> dict[str, float | None]:
    x, y, sx, sy, rotation, skew = decoder.decompose_matrix(matrix)
    return {
        "x": _finite(x),
        "y": _finite(y),
        "sx": _finite(sx),
        "sy": _finite(sy),
        "rotation": _finite(rotation),
        "skew": _finite(skew),
    }


def _identity_matrix(decoder: Any):
    return decoder.affine(1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _flat_record_by_offset(flat_layers: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for layer in flat_layers:
        try:
            offset = int(layer.get("source_offset"))
        except (TypeError, ValueError):
            continue
        result[offset] = layer
    return result


def _data_close(left: Any, right: Any, *, tolerance: float = 1e-6) -> bool:
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
        return False
    if len(left) < 6 or len(right) < 6:
        return False
    for a, b in zip(left[:6], right[:6]):
        try:
            fa = float(a)
            fb = float(b)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(fa) and math.isfinite(fb)):
            return False
        if abs(fa - fb) > tolerance * max(1.0, abs(fa), abs(fb)):
            return False
    return True


def _trace_flatten_call(
    decoder: Any,
    root: Any,
    flat_layers: list[dict[str, Any]],
    *,
    layer_start: int = 0,
    section: str | None = None,
    call_index: int = 0,
) -> dict[str, Any]:
    """Trace group ancestry without changing the flattened renderer input.

    The upstream decoder owns all transform math. This diagnostic repeats the
    exact matrix composition used by ``flatten_tree`` only to record provenance.
    ``flat_layers`` is the untouched result from the original function and is
    compared against the trace so an instrumentation bug is visible in the JSON.
    """

    groups: list[dict[str, Any]] = []
    layers: list[dict[str, Any]] = []
    group_stats: dict[str, dict[str, Any]] = {}
    flat_by_offset = _flat_record_by_offset(flat_layers)
    mismatch_offsets: list[int] = []

    def new_group_id() -> str:
        return f"c{int(call_index)}g{len(groups)}"

    def update_group_stats(group_ids: list[str], x: float | None, y: float | None) -> None:
        for group_id in group_ids:
            stats = group_stats[group_id]
            stats["descendant_layer_count"] += 1
            if x is None or y is None:
                continue
            bounds = stats["final_center_bounds"]
            if bounds is None:
                stats["final_center_bounds"] = {
                    "min_x": x,
                    "max_x": x,
                    "min_y": y,
                    "max_y": y,
                }
            else:
                bounds["min_x"] = min(bounds["min_x"], x)
                bounds["max_x"] = max(bounds["max_x"], x)
                bounds["min_y"] = min(bounds["min_y"], y)
                bounds["max_y"] = max(bounds["max_y"], y)

    def walk(
        node: Any,
        parent_matrix: Any,
        parent_group_id: str | None,
        depth: int,
        inherited_section: str | None,
        path_ids: list[str],
    ) -> None:
        group_id = new_group_id()
        current_section = getattr(node, "section", None) or inherited_section or section
        local_transform = getattr(node, "transform", None)
        node_matrix = decoder.matmul(parent_matrix, decoder.group_matrix(local_transform))
        effective_transform = _decomposed_dict(decoder, node_matrix)
        marker = getattr(node, "marker", b"") or b""
        record = {
            "group_id": group_id,
            "parent_group_id": parent_group_id,
            "depth": int(depth),
            "offset": int(getattr(node, "offset", 0) or 0),
            "source": str(getattr(node, "source", "") or ""),
            "section": str(current_section) if current_section is not None else None,
            "expected_children": getattr(node, "expected_children", None),
            "actual_children": len(list(getattr(node, "items", ()) or ())),
            "flags": int(getattr(node, "flags", 0) or 0),
            "mask": bool(getattr(node, "mask", False)),
            "marker_hex": bytes(marker).hex(),
            "local_transform": _transform_dict(local_transform),
            "effective_transform": effective_transform,
        }
        groups.append(record)
        group_stats[group_id] = {
            "descendant_layer_count": 0,
            "final_center_bounds": None,
        }
        next_path = [*path_ids, group_id]

        for item in list(getattr(node, "items", ()) or ()):
            if isinstance(item, decoder.ShapeNode):
                effective = decoder.matmul(node_matrix, decoder.shape_matrix(item))
                final_transform = _decomposed_dict(decoder, effective)
                source_offset = int(layer_start) + int(getattr(item, "offset", 0) or 0)
                flat = flat_by_offset.get(source_offset)
                trace_data = [
                    final_transform["x"],
                    final_transform["y"],
                    final_transform["sx"],
                    final_transform["sy"],
                    final_transform["rotation"],
                    final_transform["skew"],
                ]
                flat_data = flat.get("data") if isinstance(flat, dict) else None
                matches_flatten = bool(flat is not None and _data_close(trace_data, flat_data))
                if not matches_flatten:
                    mismatch_offsets.append(source_offset)

                color = list(getattr(item, "color_rgba", ()) or ())
                layers.append(
                    {
                        "source_offset": source_offset,
                        "shape_offset": int(getattr(item, "offset", 0) or 0),
                        "shape_id": int(getattr(item, "shape_id", 0) or 0),
                        "section": str(getattr(item, "section", None) or current_section or section or ""),
                        "flags": int(getattr(item, "flags", 0) or 0),
                        "mask": bool(getattr(item, "mask", False)),
                        "mask_authoritative": bool(getattr(item, "mask_authoritative", False)),
                        "is_raster_logo": bool(getattr(item, "is_raster_logo", False)),
                        "raster_id": getattr(item, "raster_id", None),
                        "color_rgba": [int(value) for value in color],
                        "local_transform": _shape_transform_dict(item),
                        "final_transform": final_transform,
                        "parent_group_id": group_id,
                        "group_depth": int(depth),
                        "group_chain": list(next_path),
                        "trace_matches_flatten": matches_flatten,
                    }
                )
                update_group_stats(
                    next_path,
                    final_transform.get("x"),
                    final_transform.get("y"),
                )
            elif isinstance(item, decoder.GroupNode):
                walk(
                    item,
                    node_matrix,
                    group_id,
                    depth + 1,
                    current_section,
                    next_path,
                )

    walk(root, _identity_matrix(decoder), None, 0, section, [])
    for group in groups:
        group.update(group_stats[group["group_id"]])

    return {
        "call_index": int(call_index),
        "requested_section": section,
        "layer_start": int(layer_start),
        "root_source": str(getattr(root, "source", "") or ""),
        "root_offset": int(getattr(root, "offset", 0) or 0),
        "flat_layer_count": len(flat_layers),
        "traced_layer_count": len(layers),
        "group_count": len(groups),
        "max_group_depth": max((int(group["depth"]) for group in groups), default=0),
        "trace_matches_flatten": not mismatch_offsets and len(layers) == len(flat_layers),
        "mismatch_offsets": mismatch_offsets[:100],
        "groups": groups,
        "layers": layers,
    }


def _diagnostic_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        root = Path(local) / "FH6GarageAnalyzer"
    else:
        root = Path.home() / ".fh6garage"
    return root / "livery_group_transform_diagnostics"


def _diagnostic_path(source: Path) -> Path:
    token = hashlib.sha1(str(source).encode("utf-8", errors="replace")).hexdigest()[:20]
    return _diagnostic_directory() / f"{source.name}-{token}-group-transform.json"


def _final_section_summary(decoded: Any) -> dict[str, Any]:
    summary: dict[str, dict[str, Any]] = {}
    for layer in list(getattr(decoded, "layers", ()) or ()):
        if not isinstance(layer, dict):
            continue
        section = str(layer.get("source_section") or layer.get("section") or "Unknown")
        entry = summary.setdefault(
            section,
            {
                "layer_count": 0,
                "min_source_offset": None,
                "max_source_offset": None,
            },
        )
        entry["layer_count"] += 1
        try:
            offset = int(layer.get("source_offset"))
        except (TypeError, ValueError):
            continue
        if entry["min_source_offset"] is None or offset < entry["min_source_offset"]:
            entry["min_source_offset"] = offset
        if entry["max_source_offset"] is None or offset > entry["max_source_offset"]:
            entry["max_source_offset"] = offset
    return summary


def _write_diagnostic(source: Path, decoded: Any, trace_calls: list[dict[str, Any]]) -> Path:
    destination = _diagnostic_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "behavior_changed_by_diagnostic_patch": False,
        "purpose": (
            "Record each flattened livery layer's parent GroupNode chain and the local/effective "
            "transforms used by the pinned KFPS decoder. The diagnostic does not modify decoding, "
            "layer order, group transforms, or rendering."
        ),
        "source_name": source.name,
        "source_path": str(source),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "final_sections": _final_section_summary(decoded),
        "decoder_report": dict(getattr(decoded, "report", {}) or {}),
        "trace_call_count": len(trace_calls),
        "trace_calls": trace_calls,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def install_group_transform_diagnostic() -> None:
    """Install non-invasive GroupNode transform provenance tracing."""
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original_flatten_tree = decoder.flatten_tree
    original_decode_forza_source = decoder.decode_forza_source

    def flatten_tree_with_trace(root, layer_start: int = 0, section: str | None = None):
        flat_layers = original_flatten_tree(root, layer_start=layer_start, section=section)
        try:
            calls = _trace_buffer()
            calls.append(
                _trace_flatten_call(
                    decoder,
                    root,
                    list(flat_layers),
                    layer_start=layer_start,
                    section=section,
                    call_index=len(calls),
                )
            )
        except Exception as exc:
            calls = _trace_buffer()
            calls.append(
                {
                    "call_index": len(calls),
                    "requested_section": section,
                    "layer_start": int(layer_start),
                    "diagnostic_error": str(exc),
                }
            )
        return flat_layers

    def decode_forza_source_with_group_trace(path, allow_locked: bool = False, game: str | None = "fh6"):
        _STATE.trace_calls = []
        decoded = original_decode_forza_source(path, allow_locked=allow_locked, game=game)
        try:
            source = Path(getattr(decoded, "source_path", path))
            destination = _write_diagnostic(source, decoded, list(_trace_buffer()))
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"[FH6_GROUP_TRACE] group transform diagnostic: {destination}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
        except Exception as exc:
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"[FH6_GROUP_TRACE] diagnostic write failed: {exc}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
        return decoded

    decoder.flatten_tree = flatten_tree_with_trace
    decoder.decode_forza_source = decode_forza_source_with_group_trace
    setattr(decoder, _PATCH_FLAG, True)
