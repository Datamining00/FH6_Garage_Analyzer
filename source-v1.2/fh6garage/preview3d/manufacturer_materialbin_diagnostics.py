from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .exact_game_asset import resolve_exact_game_asset_reference
from .materialbin_reference_helper import (
    MaterialbinReferenceHelperError,
    diagnose_materialbin_references,
)
from .native_material_textures import resolve_native_texture_reference


MANUFACTURER_MATERIALBIN_DIAGNOSTICS_FORMAT = "fh6_manufacturer_materialbin_diagnostics_v1"
MANUFACTURER_MATERIALBIN_DIAGNOSTICS_REVISION = 1
_EXACT_RESOLUTION_MODES = frozenset(
    {"vehicle_archive_exact", "game_loose_exact", "derived_zip_exact"}
)
_MAX_DIAGNOSTIC_DEPTH = 64


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
    except Exception as exc:  # injected diagnostic adapters must also fail closed
        node["status"] = "materialbin_helper_unavailable"
        node["detail"] = f"{type(exc).__name__}: {exc}"
        return node

    node["helper"] = parsed
    references, inventory_error = _ordered_references(parsed)
    if inventory_error is not None:
        # A real parse failure mirrors FTS returning null for this materialbin and
        # allows its parent to continue. A malformed/untrusted helper inventory is
        # a tooling failure and must block promotion instead.
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

            # FTS would stop on a reference that its own lookup resolves. Since a
            # filename fallback is not exact enough for P3F to promote, do not skip
            # over it and select a later reference with different semantics.
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
