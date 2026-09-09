from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .livery_paint_binding import _canonical_binding_hash, _paint_record_index
from .livery_paint_provenance import diagnose_livery_paint
from .manufacturer_colors import (
    CUSTOM_COLOR_SELECTOR,
    diagnose_manufacturer_colors_archive,
    resolve_manufacturer_selector,
)
from .material_appearance_patch import _read_glb_document


MANUFACTURER_OVERLAY_DIAGNOSTICS_FORMAT = "fh6_manufacturer_overlay_diagnostics_v1"
MANUFACTURER_OVERLAY_DIAGNOSTICS_REVISION = 1


def _u32(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 0xFFFFFFFF else None


def _clean_material_name(value: Any) -> str:
    return str(value or "").strip()


def _exact_material_entry_matches(group: Any, material_name: str) -> list[dict[str, Any]]:
    if not isinstance(group, dict) or not material_name:
        return []
    target = material_name.casefold()
    matches: list[dict[str, Any]] = []
    for raw_entry in group.get("entries") or []:
        if not isinstance(raw_entry, dict):
            continue
        names = raw_entry.get("material_names") or []
        if not isinstance(names, (list, tuple)):
            continue
        if any(
            isinstance(name, str) and name.strip().casefold() == target
            for name in names
        ):
            matches.append(raw_entry)
    return matches


def _preview_rgb(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    output: list[float] = []
    for component in value[:3]:
        if isinstance(component, bool):
            return None
        try:
            number = float(component)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        output.append(number)
    return output


def _uv4_contract(
    primitive: dict[str, Any],
    accessors: list[Any],
) -> dict[str, Any]:
    attrs = primitive.get("attributes") or {}
    if not isinstance(attrs, dict) or "TEXCOORD_4" not in attrs:
        return {
            "status": "uv4_missing",
            "present": False,
            "accessor_index": None,
            "component_type": None,
            "accessor_type": None,
            "count": None,
            "position_count": None,
        }

    try:
        uv_index = int(attrs["TEXCOORD_4"])
    except (TypeError, ValueError):
        return {
            "status": "uv4_accessor_invalid",
            "present": True,
            "accessor_index": None,
            "component_type": None,
            "accessor_type": None,
            "count": None,
            "position_count": None,
        }
    if uv_index < 0 or uv_index >= len(accessors) or not isinstance(accessors[uv_index], dict):
        return {
            "status": "uv4_accessor_invalid",
            "present": True,
            "accessor_index": uv_index,
            "component_type": None,
            "accessor_type": None,
            "count": None,
            "position_count": None,
        }

    accessor = accessors[uv_index]
    component_type = accessor.get("componentType")
    accessor_type = accessor.get("type")
    try:
        uv_count = int(accessor.get("count"))
    except (TypeError, ValueError):
        uv_count = None

    position_count = None
    try:
        position_index = int(attrs.get("POSITION"))
    except (TypeError, ValueError):
        position_index = -1
    if 0 <= position_index < len(accessors) and isinstance(accessors[position_index], dict):
        try:
            position_count = int(accessors[position_index].get("count"))
        except (TypeError, ValueError):
            position_count = None

    valid = (
        component_type == 5126
        and accessor_type == "VEC2"
        and uv_count is not None
        and uv_count > 0
        and position_count is not None
        and uv_count == position_count
    )
    return {
        "status": "uv4_exact_kfps_accessor" if valid else "uv4_accessor_contract_invalid",
        "present": True,
        "accessor_index": uv_index,
        "component_type": component_type,
        "accessor_type": accessor_type,
        "count": uv_count,
        "position_count": position_count,
    }


def build_manufacturer_overlay_diagnostics(
    glb_path: str | Path,
    paint_provenance: Any,
    manufacturer_colors: Any,
) -> dict[str, Any]:
    """Diagnose the exact FH6 manufacturer swatch overlay boundary without rendering.

    P3D deliberately narrows the public ForzaTechStudio behavior. FTS may broaden
    manufacturer targeting with material/path token matching; FH6 Assistant does
    not copy that heuristic. A candidate exists only when the KFPS mesh is role
    ``paint``, its exact unprefixed X16 material binding resolves to one unique
    C_livery paint record, that record selects one manufacturer group, exactly one
    entry in that group names the exact KFPS ``kfps_material_name``
    (OrdinalIgnoreCase semantics), and the primitive exports a valid float VEC2
    ``TEXCOORD_4`` accessor with the same vertex count as POSITION.

    Entry Path is preserved only as provenance. Texture resolution, Durango detile,
    swatch material semantics, UV4 texture sampling, tint composition, and actual
    rendering remain disabled.
    """
    records, ambiguous_hashes, record_issues = _paint_record_index(paint_provenance)
    raw_records = (
        paint_provenance.get("records") or []
        if isinstance(paint_provenance, dict)
        else []
    )
    global_custom_primary_active = any(
        bool(record.get("primary_color_enabled"))
        for record in raw_records
        if isinstance(record, dict)
    )

    report: dict[str, Any] = {
        "format": MANUFACTURER_OVERLAY_DIAGNOSTICS_FORMAT,
        "revision": MANUFACTURER_OVERLAY_DIAGNOSTICS_REVISION,
        "status": "manufacturer_overlay_diagnostics_unavailable",
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
        "binding_format": "kfps_material_binding_hash_x16_unprefixed",
        "material_match_contract": "exact_kfps_material_name_to_fh6_v2_entry_material_names_case_insensitive",
        "uv_contract": "exact_kfps_texcoord_4_float_vec2_position_count_match",
        "global_custom_primary_active": global_custom_primary_active,
        "manufacturer_global_gate": (
            "suppressed_by_explicit_custom_primary"
            if global_custom_primary_active
            else "manufacturer_overlay_structural_diagnostics_allowed"
        ),
        "paint_primitive_count": 0,
        "evaluated_binding_count": 0,
        "exact_candidate_count": 0,
        "globally_suppressed_count": 0,
        "ambiguous_binding_count": 0,
        "ambiguous_entry_count": 0,
        "missing_material_name_count": 0,
        "unmatched_entry_count": 0,
        "missing_or_invalid_uv4_count": 0,
        "candidates": [],
        "issues": list(record_issues),
        "interpretation_boundary": (
            "Paint P3D inventories exact manufacturer overlay candidates only. It does not resolve/decode entry Path "
            "swatchbins, infer material targets from mesh names or path substrings, sample UV4, apply manufacturer "
            "tint/alpha, emulate finish shaders, or alter FH6 game/save data."
        ),
    }
    if not isinstance(paint_provenance, dict) or paint_provenance.get("status") != "paint_descriptor_parsed":
        report["issues"].append("C_livery paint provenance is unavailable or unresolved.")
        return report
    if not isinstance(manufacturer_colors, dict) or manufacturer_colors.get("status") != "manufacturer_colors_parsed":
        report["issues"].append("ManufacturerColors provenance is unavailable or unresolved.")
        return report

    document = _read_glb_document(Path(glb_path))
    meshes = document.get("meshes") or []
    accessors = document.get("accessors") or []
    if not isinstance(meshes, list) or not isinstance(accessors, list):
        report["issues"].append("GLB mesh/accessor structure is unavailable.")
        return report

    node_extras_by_mesh: dict[int, dict[str, Any]] = {}
    for node in document.get("nodes") or []:
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        try:
            mesh_index = int(node["mesh"])
        except (TypeError, ValueError):
            continue
        if 0 <= mesh_index < len(meshes):
            node_extras_by_mesh[mesh_index] = dict(node.get("extras") or {})

    rows: list[dict[str, Any]] = []
    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            continue
        extras = dict(node_extras_by_mesh.get(mesh_index) or {})
        extras.update(mesh.get("extras") or {})
        role = str(extras.get("kfps_role") or "").strip().casefold()
        if role != "paint":
            continue
        primitives = mesh.get("primitives") or []
        if not isinstance(primitives, list):
            continue
        material_name = _clean_material_name(extras.get("kfps_material_name"))
        binding_hash = _canonical_binding_hash(extras.get("kfps_material_binding_hash"))

        for primitive_index, primitive in enumerate(primitives):
            if not isinstance(primitive, dict):
                continue
            report["paint_primitive_count"] += 1
            row: dict[str, Any] = {
                "mesh_index": mesh_index,
                "primitive_index": primitive_index,
                "mesh_name": str(mesh.get("name") or ""),
                "role": "paint",
                "material_hash": f"0x{binding_hash:016X}" if binding_hash is not None else None,
                "material_name": material_name or None,
                "selector": None,
                "group_index": None,
                "entry_index": None,
                "entry_material_names": [],
                "entry_path": None,
                "entry_preview_color": None,
                "uv4": _uv4_contract(primitive, accessors),
                "rendering_enabled": False,
                "status": "unresolved",
            }

            if binding_hash is None:
                row["status"] = "binding_hash_invalid"
                rows.append(row)
                continue
            if binding_hash in ambiguous_hashes:
                report["ambiguous_binding_count"] += 1
                row["status"] = "binding_record_ambiguous"
                rows.append(row)
                continue
            record = records.get(binding_hash)
            if record is None:
                row["status"] = "binding_record_unmatched"
                rows.append(row)
                continue
            report["evaluated_binding_count"] += 1

            selector = _u32(record.get("manufacturer_color_selector"))
            row["selector"] = selector
            if selector is None:
                row["status"] = "manufacturer_selector_invalid"
                rows.append(row)
                continue
            if selector == CUSTOM_COLOR_SELECTOR:
                row["status"] = "custom_selector_no_manufacturer_overlay"
                rows.append(row)
                continue
            if global_custom_primary_active:
                report["globally_suppressed_count"] += 1
                row["status"] = "manufacturer_overlay_suppressed_by_global_custom_paint"
                rows.append(row)
                continue

            resolved = resolve_manufacturer_selector(manufacturer_colors, selector)
            if resolved.get("status") != "manufacturer_group_resolved":
                row["status"] = str(resolved.get("status") or "manufacturer_group_unresolved")
                rows.append(row)
                continue
            group = resolved.get("group")
            if isinstance(group, dict):
                try:
                    row["group_index"] = int(group.get("index"))
                except (TypeError, ValueError):
                    row["group_index"] = None

            if not material_name:
                report["missing_material_name_count"] += 1
                row["status"] = "kfps_material_name_missing"
                rows.append(row)
                continue

            matches = _exact_material_entry_matches(group, material_name)
            if not matches:
                report["unmatched_entry_count"] += 1
                row["status"] = "manufacturer_entry_not_targeted_by_exact_material_name"
                rows.append(row)
                continue
            if len(matches) != 1:
                report["ambiguous_entry_count"] += 1
                row["status"] = "manufacturer_entry_material_name_ambiguous"
                row["matching_entry_indices"] = [entry.get("index") for entry in matches]
                rows.append(row)
                continue

            entry = matches[0]
            try:
                row["entry_index"] = int(entry.get("index"))
            except (TypeError, ValueError):
                row["entry_index"] = None
            names = entry.get("material_names") or []
            row["entry_material_names"] = [str(value) for value in names if isinstance(value, str)]
            entry_path = str(entry.get("path") or "").strip()
            row["entry_path"] = entry_path or None
            row["entry_preview_color"] = _preview_rgb(entry.get("preview_color"))

            if not entry_path:
                row["status"] = "manufacturer_entry_path_missing"
                rows.append(row)
                continue
            normalized_path = entry_path.replace("\\", "/")
            if not normalized_path.casefold().endswith(".swatchbin"):
                row["status"] = "manufacturer_entry_path_not_swatchbin"
                rows.append(row)
                continue
            if row["uv4"]["status"] != "uv4_exact_kfps_accessor":
                report["missing_or_invalid_uv4_count"] += 1
                row["status"] = row["uv4"]["status"]
                rows.append(row)
                continue

            report["exact_candidate_count"] += 1
            row["status"] = "exact_manufacturer_overlay_candidate_diagnosed"
            rows.append(row)

    report["candidates"] = rows
    report["status"] = "manufacturer_overlay_candidates_diagnosed"
    return report


def diagnose_manufacturer_overlay(
    glb_path: str | Path,
    paint_source: str | Path,
    vehicle_archive: str | Path,
) -> dict[str, Any]:
    """Run the read-only P3D diagnostic from actual GLB/C_livery/car-archive inputs."""
    paint_report = diagnose_livery_paint(paint_source)
    manufacturer_report = diagnose_manufacturer_colors_archive(vehicle_archive)
    result = build_manufacturer_overlay_diagnostics(
        glb_path,
        paint_report,
        manufacturer_report,
    )
    result = dict(result)
    result["glb_file"] = str(Path(glb_path))
    result["paint_source"] = str(Path(paint_source))
    result["vehicle_archive"] = str(Path(vehicle_archive))
    return result
