from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .exact_game_asset import resolve_exact_game_asset_reference
from .materialbin_reference_helper import (
    MaterialbinReferenceHelperError,
    diagnose_materialbin_references,
)
from .native_material_textures import resolve_native_texture_reference


MANUFACTURER_MATERIALBIN_DIAGNOSTICS_FORMAT = "fh6_manufacturer_materialbin_diagnostics_v1"
MANUFACTURER_MATERIALBIN_DIAGNOSTICS_REVISION = 2
_EXACT_RESOLUTION_MODES = frozenset(
    {"vehicle_archive_exact", "game_loose_exact", "derived_zip_exact"}
)
_MAX_DIAGNOSTIC_DEPTH = 64
_MAX_P3D_BREAKDOWN_SAMPLES = 12


def _report_value(mapping: Any, snake: str, camel: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    if snake in mapping:
        return mapping[snake]
    return mapping.get(camel)


def _ordered_references(report: Any) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(report, dict):
        return [], "materialbin_helper_report_invalid"
    status = _report_value(report, "status", "status")
    if status != "materialbin_references_parsed":
        return [], str(status or "materialbin_helper_report_unresolved")
    raw = _report_value(report, "references", "references")
    if not isinstance(raw, list):
        return [], "materialbin_reference_inventory_invalid"
    rows: list[dict[str, Any]] = []
    for expected_order, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], "materialbin_reference_inventory_invalid"
        order = _report_value(item, "order", "order")
        if isinstance(order, bool):
            return [], "materialbin_reference_order_invalid"
        try:
            parsed_order = int(order)
        except (TypeError, ValueError):
            return [], "materialbin_reference_order_invalid"
        if parsed_order != expected_order:
            return [], "materialbin_reference_order_invalid"
        reference_path = str(
            _report_value(item, "reference_path", "referencePath") or ""
        ).strip()
        if not reference_path:
            return [], "materialbin_reference_path_invalid"
        rows.append(item)
    return rows, None


def _p3d_breakdown(p3d_report: Any) -> dict[str, Any]:
    """Summarize where P3D paint primitives stop before P3F promotion.

    P3D already records one fail-closed terminal status for every paint primitive.
    This function is diagnostic-only: it does not change candidate eligibility.
    """
    summary: dict[str, Any] = {
        "status": "p3d_breakdown_unavailable",
        "paint_primitive_count": 0,
        "evaluated_binding_count": 0,
        "exact_swatch_candidate_count": 0,
        "with_material_name_count": 0,
        "with_binding_hash_count": 0,
        "resolved_manufacturer_group_count": 0,
        "matched_manufacturer_entry_count": 0,
        "with_entry_path_count": 0,
        "entry_path_kind_counts": {
            "missing": 0,
            "swatchbin": 0,
            "materialbin": 0,
            "other": 0,
        },
        "uv4_status_counts": {},
        "row_status_counts": {},
        "p3f_materialbin_deferred_count": 0,
        "p3f_materialbin_uv4_ready_count": 0,
        "diagnostic_focus": "p3d_report_unavailable",
        "rejection_samples": [],
    }
    if not isinstance(p3d_report, dict):
        return summary

    def _as_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    summary["paint_primitive_count"] = _as_int(
        p3d_report.get("paint_primitive_count")
    )
    summary["evaluated_binding_count"] = _as_int(
        p3d_report.get("evaluated_binding_count")
    )
    summary["exact_swatch_candidate_count"] = _as_int(
        p3d_report.get("exact_candidate_count")
    )

    rows = p3d_report.get("candidates") or []
    if not isinstance(rows, list):
        summary["diagnostic_focus"] = "p3d_candidate_inventory_malformed"
        return summary

    status_counts: Counter[str] = Counter()
    uv4_counts: Counter[str] = Counter()
    path_counts: Counter[str] = Counter()
    material_name_count = 0
    binding_hash_count = 0
    resolved_group_count = 0
    matched_entry_count = 0
    entry_path_count = 0
    p3f_materialbin_count = 0
    p3f_materialbin_uv4_ready_count = 0
    samples_by_status: dict[str, dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "status_missing")
        status_counts[status] += 1

        material_name = str(row.get("material_name") or "").strip()
        material_hash = str(row.get("material_hash") or "").strip()
        if material_name:
            material_name_count += 1
        if material_hash:
            binding_hash_count += 1
        if row.get("group_index") is not None:
            resolved_group_count += 1
        if row.get("entry_index") is not None:
            matched_entry_count += 1

        uv4 = row.get("uv4") if isinstance(row.get("uv4"), dict) else {}
        uv4_status = str(uv4.get("status") or "uv4_status_missing")
        uv4_counts[uv4_status] += 1

        entry_path = str(row.get("entry_path") or "").strip()
        if not entry_path:
            path_kind = "missing"
        else:
            entry_path_count += 1
            normalized = entry_path.replace("\\", "/").casefold()
            if normalized.endswith(".swatchbin"):
                path_kind = "swatchbin"
            elif normalized.endswith(".materialbin"):
                path_kind = "materialbin"
            else:
                path_kind = "other"
        path_counts[path_kind] += 1

        is_p3f_materialbin = (
            status == "manufacturer_entry_path_not_swatchbin"
            and path_kind == "materialbin"
        )
        if is_p3f_materialbin:
            p3f_materialbin_count += 1
            if uv4_status == "uv4_exact_kfps_accessor":
                p3f_materialbin_uv4_ready_count += 1

        if (
            status != "exact_manufacturer_overlay_candidate_diagnosed"
            and status not in samples_by_status
            and len(samples_by_status) < _MAX_P3D_BREAKDOWN_SAMPLES
        ):
            samples_by_status[status] = {
                "status": status,
                "mesh_index": row.get("mesh_index"),
                "primitive_index": row.get("primitive_index"),
                "mesh_name": row.get("mesh_name"),
                "material_name": row.get("material_name"),
                "material_hash": row.get("material_hash"),
                "selector": row.get("selector"),
                "group_index": row.get("group_index"),
                "entry_index": row.get("entry_index"),
                "entry_path": row.get("entry_path"),
                "entry_path_kind": path_kind,
                "uv4_status": uv4_status,
                "uv4_count": uv4.get("count"),
                "position_count": uv4.get("position_count"),
            }

    summary.update(
        {
            "status": "p3d_breakdown_diagnosed",
            "with_material_name_count": material_name_count,
            "with_binding_hash_count": binding_hash_count,
            "resolved_manufacturer_group_count": resolved_group_count,
            "matched_manufacturer_entry_count": matched_entry_count,
            "with_entry_path_count": entry_path_count,
            "entry_path_kind_counts": {
                key: int(path_counts.get(key, 0))
                for key in ("missing", "swatchbin", "materialbin", "other")
            },
            "uv4_status_counts": dict(sorted(uv4_counts.items())),
            "row_status_counts": dict(sorted(status_counts.items())),
            "p3f_materialbin_deferred_count": p3f_materialbin_count,
            "p3f_materialbin_uv4_ready_count": p3f_materialbin_uv4_ready_count,
            "rejection_samples": list(samples_by_status.values()),
        }
    )

    if summary["paint_primitive_count"] == 0 and not rows:
        focus = "no_paint_primitives_exported"
    elif p3f_materialbin_count > 0:
        focus = (
            "materialbin_candidates_present_uv4_ready"
            if p3f_materialbin_uv4_ready_count > 0
            else "materialbin_candidates_present_but_uv4_not_ready"
        )
    elif status_counts:
        dominant_status, dominant_count = status_counts.most_common(1)[0]
        focus = f"no_materialbin_candidate_dominant_status:{dominant_status}:{dominant_count}"
    else:
        focus = "paint_rows_missing_despite_reported_paint_primitives"
    summary["diagnostic_focus"] = focus
    return summary


def _trace_materialbin(
    reference_path: str,
    vehicle_archive: str | Path,
    cache_root: str | Path,
    *,
    resolve_asset: Callable[..., Any],
    resolve_swatch: Callable[..., Any],
    analyze_materialbin: Callable[..., dict[str, Any]],
    lineage: tuple[str, ...],
    active_paths: frozenset[str],
    depth: int,
) -> dict[str, Any]:
    normalized_key = reference_path.replace("\\", "/").strip().casefold()
    node: dict[str, Any] = {
        "reference_path": reference_path,
        "depth": depth,
        "status": "materialbin_unresolved",
        "asset": None,
        "references": [],
        "selected_swatch": None,
        "selected_lineage": list(lineage),
        "rendering_enabled": False,
    }
    if depth > _MAX_DIAGNOSTIC_DEPTH:
        node["status"] = "materialbin_depth_limit_deferred"
        return node
    if normalized_key in active_paths:
        node["status"] = "materialbin_cycle_deferred"
        return node

    asset = resolve_asset(reference_path, vehicle_archive, cache_root)
    asset_dict = asset.as_dict() if hasattr(asset, "as_dict") else dict(asset)
    node["asset"] = asset_dict
    if asset_dict.get("status") != "resolved_payload" or asset_dict.get("resolution_mode") not in _EXACT_RESOLUTION_MODES:
        node["status"] = "materialbin_asset_unresolved_exact"
        return node
    cache_path = asset_dict.get("cache_path")
    if not cache_path:
        node["status"] = "materialbin_asset_cache_unavailable"
        return node

    try:
        parsed = analyze_materialbin(cache_path)
    except MaterialbinReferenceHelperError as exc:
        node["status"] = "materialbin_helper_unavailable"
        node["detail"] = str(exc)
        return node
    except Exception as exc:
        node["status"] = "materialbin_helper_unavailable"
        node["detail"] = f"{type(exc).__name__}: {exc}"
        return node

    node["helper"] = parsed
    references, inventory_error = _ordered_references(parsed)
    if inventory_error is not None:
        if inventory_error == "materialbin_parse_failed":
            node["status"] = "materialbin_parse_failed"
        else:
            node["status"] = inventory_error
        return node

    current_active = active_paths | {normalized_key}
    next_lineage = lineage + (reference_path,)
    attempts: list[dict[str, Any]] = []
    for index, raw in enumerate(references):
        child_path = str(_report_value(raw, "reference_path", "referencePath") or "").strip()
        source_kind = str(_report_value(raw, "source_kind", "sourceKind") or "")
        source_field = str(_report_value(raw, "source_field", "sourceField") or "")
        attempt: dict[str, Any] = {
            "order": index,
            "source_kind": source_kind,
            "source_field": source_field,
            "parameter_hash": str(_report_value(raw, "parameter_hash", "parameterHash") or ""),
            "path_hash": str(_report_value(raw, "path_hash", "pathHash") or ""),
            "reference_path": child_path,
            "status": "unresolved",
        }

        if child_path.replace("\\", "/").casefold().endswith(".materialbin"):
            nested = _trace_materialbin(
                child_path,
                vehicle_archive,
                cache_root,
                resolve_asset=resolve_asset,
                resolve_swatch=resolve_swatch,
                analyze_materialbin=analyze_materialbin,
                lineage=next_lineage,
                active_paths=current_active,
                depth=depth + 1,
            )
            attempt["nested"] = nested
            nested_status = str(nested.get("status") or "")
            if nested.get("selected_swatch") is not None:
                attempt["status"] = "nested_materialbin_selected_exact_swatch"
                attempts.append(attempt)
                node["references"] = attempts
                node["selected_swatch"] = nested["selected_swatch"]
                node["selected_lineage"] = nested.get("selected_lineage") or list(next_lineage)
                node["status"] = "materialbin_selected_exact_swatch"
                return node
            if nested_status in {
                "materialbin_helper_unavailable",
                "materialbin_reference_inventory_invalid",
                "materialbin_reference_order_invalid",
                "materialbin_reference_path_invalid",
                "materialbin_helper_report_invalid",
            }:
                attempt["status"] = "nested_materialbin_tooling_blocked"
                attempts.append(attempt)
                node["references"] = attempts
                node["status"] = "materialbin_traversal_tooling_blocked"
                return node
            attempt["status"] = nested_status or "nested_materialbin_unresolved"
            attempts.append(attempt)
            continue

        payload = resolve_swatch(child_path, vehicle_archive, cache_root)
        payload_dict = payload.as_dict() if hasattr(payload, "as_dict") else dict(payload)
        attempt["payload"] = payload_dict
        if payload_dict.get("status") == "resolved_payload":
            mode = str(payload_dict.get("resolution_mode") or "")
            if mode in _EXACT_RESOLUTION_MODES:
                attempt["status"] = "swatch_resolved_exact"
                attempts.append(attempt)
                selected = {
                    "reference_order": index,
                    "source_kind": source_kind,
                    "source_field": source_field,
                    "parameter_hash": attempt["parameter_hash"],
                    "path_hash": attempt["path_hash"],
                    "reference_path": child_path,
                    "payload": payload_dict,
                }
                node["references"] = attempts
                node["selected_swatch"] = selected
                node["selected_lineage"] = list(next_lineage) + [child_path]
                node["status"] = "materialbin_selected_exact_swatch"
                return node

            attempt["status"] = "swatch_nonexact_resolution_blocks_order"
            attempts.append(attempt)
            node["references"] = attempts
            node["status"] = "materialbin_blocked_by_nonexact_resolution"
            return node

        attempt["status"] = "swatch_unresolved"
        attempts.append(attempt)

    node["references"] = attempts
    node["status"] = "materialbin_no_exact_swatch_resolved"
    return node


def trace_manufacturer_materialbin_payloads(
    p3d_report: Any,
    vehicle_archive: str | Path,
    cache_root: str | Path,
    *,
    resolve_asset: Callable[..., Any] = resolve_exact_game_asset_reference,
    resolve_swatch: Callable[..., Any] = resolve_native_texture_reference,
    analyze_materialbin: Callable[..., dict[str, Any]] = diagnose_materialbin_references,
) -> dict[str, Any]:
    """Trace P3D .materialbin entries to the first exact swatchbin, without rendering."""
    report: dict[str, Any] = {
        "format": MANUFACTURER_MATERIALBIN_DIAGNOSTICS_FORMAT,
        "revision": MANUFACTURER_MATERIALBIN_DIAGNOSTICS_REVISION,
        "status": "manufacturer_materialbin_diagnostics_unavailable",
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
        "candidate_count": 0,
        "exact_resolved_count": 0,
        "blocked_count": 0,
        "unresolved_count": 0,
        "traces": [],
        "issues": [],
        "p3d_breakdown": _p3d_breakdown(p3d_report),
        "interpretation_boundary": (
            "Paint P3F follows only P3D-exact manufacturer entries whose Path is .materialbin. "
            "Materialbin bytes are located only by vehicle_archive_exact, game_loose_exact, or derived_zip_exact; "
            "the SHA-verified KFPS/ForzaTools helper exports MatL Path/PathV1_1/PathV1_2 references first and "
            "Texture2D references second, preserving FTS traversal order. Filename fallback can block but never "
            "promote a result. DDS decode/detile, UV4 sampling, tint/alpha composition, finish shaders, rendering, "
            "and FH6 game/save writes remain disabled."
        ),
    }
    if not isinstance(p3d_report, dict) or p3d_report.get("status") != "manufacturer_overlay_candidates_diagnosed":
        report["issues"].append("P3D manufacturer overlay diagnostics are unavailable or unresolved.")
        return report
    rows = p3d_report.get("candidates") or []
    if not isinstance(rows, list):
        report["issues"].append("P3D candidate inventory is malformed.")
        return report

    traces: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry_path = str(row.get("entry_path") or "").strip()
        if row.get("status") != "manufacturer_entry_path_not_swatchbin":
            continue
        if not entry_path.replace("\\", "/").casefold().endswith(".materialbin"):
            continue

        report["candidate_count"] += 1
        uv4 = row.get("uv4") if isinstance(row.get("uv4"), dict) else {}
        trace: dict[str, Any] = {
            "mesh_index": row.get("mesh_index"),
            "primitive_index": row.get("primitive_index"),
            "material_hash": row.get("material_hash"),
            "material_name": row.get("material_name"),
            "selector": row.get("selector"),
            "group_index": row.get("group_index"),
            "entry_index": row.get("entry_index"),
            "entry_path": entry_path,
            "uv4_status": uv4.get("status"),
            "status": "manufacturer_materialbin_unresolved",
            "selected_swatch": None,
            "rendering_enabled": False,
        }
        if uv4.get("status") != "uv4_exact_kfps_accessor":
            trace["status"] = "manufacturer_materialbin_uv4_contract_deferred"
            report["unresolved_count"] += 1
            traces.append(trace)
            continue

        root = _trace_materialbin(
            entry_path,
            vehicle_archive,
            cache_root,
            resolve_asset=resolve_asset,
            resolve_swatch=resolve_swatch,
            analyze_materialbin=analyze_materialbin,
            lineage=(),
            active_paths=frozenset(),
            depth=0,
        )
        trace["root"] = root
        trace["selected_swatch"] = root.get("selected_swatch")
        root_status = str(root.get("status") or "")
        if root_status == "materialbin_selected_exact_swatch":
            trace["status"] = "manufacturer_materialbin_swatch_resolved_exact"
            report["exact_resolved_count"] += 1
        elif root_status in {
            "materialbin_blocked_by_nonexact_resolution",
            "materialbin_traversal_tooling_blocked",
            "materialbin_helper_unavailable",
            "materialbin_depth_limit_deferred",
        }:
            trace["status"] = "manufacturer_materialbin_traversal_blocked"
            report["blocked_count"] += 1
        else:
            trace["status"] = "manufacturer_materialbin_swatch_unresolved"
            report["unresolved_count"] += 1
        traces.append(trace)

    report["traces"] = traces
    report["status"] = "manufacturer_materialbin_payloads_diagnosed"
    return report
