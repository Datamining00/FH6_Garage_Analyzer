from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from pathlib import Path
from typing import Any


_PATCH_FLAG = "_fh6assistant_parent_ownership_diagnostic_v1"
_STATE = threading.local()


def _trace_buffer() -> list[dict[str, Any]]:
    value = getattr(_STATE, "ownership_calls", None)
    if value is None:
        value = []
        _STATE.ownership_calls = value
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


def _shape_stats(decoder: Any, node: Any, layer_start: int) -> dict[str, Any]:
    offsets: list[int] = []
    group_count = 0
    shape_count = 0

    def walk(item: Any) -> None:
        nonlocal group_count, shape_count
        if isinstance(item, decoder.ShapeNode):
            shape_count += 1
            offsets.append(int(layer_start) + int(getattr(item, "offset", 0) or 0))
            return
        if isinstance(item, decoder.GroupNode):
            group_count += 1
            for child in list(getattr(item, "items", ()) or ()):
                walk(child)

    walk(node)
    return {
        "descendant_shape_count": int(shape_count),
        "descendant_group_count": int(group_count),
        "min_shape_source_offset": min(offsets) if offsets else None,
        "max_shape_source_offset": max(offsets) if offsets else None,
    }


def _node_summary(decoder: Any, node: Any, layer_start: int) -> dict[str, Any]:
    if isinstance(node, decoder.ShapeNode):
        return {
            "node_type": "shape",
            "offset": int(getattr(node, "offset", 0) or 0),
            "source_offset": int(layer_start) + int(getattr(node, "offset", 0) or 0),
            "shape_id": int(getattr(node, "shape_id", 0) or 0),
            "flags": int(getattr(node, "flags", 0) or 0),
            "mask": bool(getattr(node, "mask", False)),
        }

    items = list(getattr(node, "items", ()) or ())
    result = {
        "node_type": "group",
        "offset": int(getattr(node, "offset", 0) or 0),
        "source_offset": int(layer_start) + int(getattr(node, "offset", 0) or 0),
        "source": str(getattr(node, "source", "") or ""),
        "expected_children": getattr(node, "expected_children", None),
        "actual_children": len(items),
        "flags": int(getattr(node, "flags", 0) or 0),
        "mask": bool(getattr(node, "mask", False)),
        "marker_hex": bytes(getattr(node, "marker", b"") or b"").hex(),
        "local_transform": _transform_dict(getattr(node, "transform", None)),
    }
    result.update(_shape_stats(decoder, node, int(layer_start)))
    return result


def summarize_ownership_call(
    decoder: Any,
    root: Any,
    *,
    layer_start: int = 0,
    section: str | None = None,
    call_index: int = 0,
) -> dict[str, Any]:
    """Describe the final post-recovery GroupNode ownership tree without mutating it."""

    implicit_parents: list[dict[str, Any]] = []
    all_groups: list[dict[str, Any]] = []

    def walk(group: Any, ancestors: list[dict[str, Any]], depth: int) -> None:
        summary = _node_summary(decoder, group, int(layer_start))
        summary["depth"] = int(depth)
        summary["ancestor_group_offsets"] = [item["source_offset"] for item in ancestors]
        summary["ancestor_group_sources"] = [item["source"] for item in ancestors]
        all_groups.append(summary)

        items = list(getattr(group, "items", ()) or ())
        if str(getattr(group, "source", "") or "") == "implicit_bare_transform_pair":
            implicit_parents.append(
                {
                    **summary,
                    "direct_children": [
                        _node_summary(decoder, child, int(layer_start))
                        for child in items
                    ],
                }
            )

        next_ancestors = [*ancestors, summary]
        for child in items:
            if isinstance(child, decoder.GroupNode):
                walk(child, next_ancestors, depth + 1)

    walk(root, [], 0)
    root_children = [
        _node_summary(decoder, child, int(layer_start))
        for child in list(getattr(root, "items", ()) or ())
    ]
    return {
        "call_index": int(call_index),
        "requested_section": section,
        "layer_start": int(layer_start),
        "root_source": str(getattr(root, "source", "") or ""),
        "root_offset": int(getattr(root, "offset", 0) or 0),
        "root_direct_children": root_children,
        "implicit_parent_count": len(implicit_parents),
        "implicit_parents": implicit_parents,
        "group_count": len(all_groups),
        "all_groups": all_groups,
    }


def _diagnostic_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        root = Path(local) / "FH6GarageAnalyzer"
    else:
        root = Path.home() / ".fh6garage"
    target = root / "livery_parent_ownership_diagnostics"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _diagnostic_path(source: Path) -> Path:
    token = hashlib.sha1(str(source.resolve()).encode("utf-8", errors="replace")).hexdigest()[:20]
    return _diagnostic_directory() / f"{source.name}-{token}-parent-ownership.json"


def install_livery_parent_ownership_diagnostic() -> None:
    """Trace final GroupNode ownership after all decoder recovery patches are active."""
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original_flatten_tree = decoder.flatten_tree
    original_decode_forza_source = decoder.decode_forza_source

    def flatten_tree_with_ownership(root, layer_start: int = 0, section: str | None = None):
        try:
            calls = _trace_buffer()
            calls.append(
                summarize_ownership_call(
                    decoder,
                    root,
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
        return original_flatten_tree(root, layer_start=layer_start, section=section)

    def decode_with_ownership(path, allow_locked: bool = False, game: str | None = "fh6"):
        _STATE.ownership_calls = []
        decoded = original_decode_forza_source(path, allow_locked=allow_locked, game=game)
        try:
            if str(getattr(decoded, "source_kind", "")).casefold() != "clivery":
                return decoded
            source = Path(getattr(decoded, "source_path", path))
            document = {
                "purpose": (
                    "Record the final post-recovery C_livery GroupNode ownership tree, especially "
                    "implicit bare-transform parents and their direct children. The diagnostic does "
                    "not change decoding, transforms, masks, layer order, or rendering."
                ),
                "behavior_changed_by_diagnostic": False,
                "source_name": source.name,
                "source_path": str(source),
                "trace_call_count": len(_trace_buffer()),
                "trace_calls": list(_trace_buffer()),
            }
            destination = _diagnostic_path(source)
            destination.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"[FH6_PARENT_OWNERSHIP_TRACE] {destination}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
        except Exception as exc:
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"[FH6_PARENT_OWNERSHIP_TRACE] diagnostic failed: {exc}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
        return decoded

    decoder.flatten_tree = flatten_tree_with_ownership
    decoder.decode_forza_source = decode_with_ownership
    setattr(decoder, _PATCH_FLAG, True)
