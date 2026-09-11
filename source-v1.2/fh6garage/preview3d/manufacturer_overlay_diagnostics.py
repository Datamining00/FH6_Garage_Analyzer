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
MANUFACTURER_OVERLAY_DIAGNOSTICS_REVISION = 3
_BUILTIN_MANUFACTURER_MATERIAL_NAMES = frozenset({"carpaint", "carpaint_secondary"})
_MAX_GROUP_INVENTORY_ENTRIES = 64
_PREVIEW_MATCH_ABS_TOLERANCE = 1e-6


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


def _group_entries(group: Any) -> list[dict[str, Any]]:
    if not isinstance(group, dict):
        return []
    return [entry for entry in (group.get("entries") or []) if isinstance(entry, dict)]


def _entry_path_kind(value: Any) -> str:
    path = str(value or "").strip().replace("\\", "/").casefold()
    if not path:
        return "missing"
    if path.endswith(".swatchbin"):
        return "swatchbin"
    if path.endswith(".materialbin"):
        return "materialbin"
    return "other"


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


def _preview_rgb_equal(left: Any, right: Any) -> bool:
    a = _preview_rgb(left)
    b = _preview_rgb(right)
    if a is None or b is None:
        return False
    return all(
        math.isclose(x, y, rel_tol=0.0, abs_tol=_PREVIEW_MATCH_ABS_TOLERANCE)
        for x, y in zip(a, b)
    )


def _preview_entry_matches(group: Any, *, secondary: bool) -> list[dict[str, Any]]:
    if not isinstance(group, dict):
        return []
    present_key = (
        "secondary_group_preview_present"
        if secondary
        else "primary_group_preview_present"
    )
    color_key = (
        "secondary_group_preview_color"
        if secondary
        else "primary_group_preview_color"
    )
    if not bool(group.get(present_key)):
        return []
    target = group.get(color_key)
    if _preview_rgb(target) is None:
        return []
    return [
        entry
        for entry in _group_entries(group)
        if _preview_rgb_equal(entry.get("preview_color"), target)
    ]


def _same_path_preview_match(
    entries: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[Any]]:
    """Return one representative only when all preview matches share one exact path."""
    if not entries:
        return None, []
    paths: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            return None, [item.get("index") for item in entries]
        normalized = raw_path.replace("\\", "/").casefold()
        paths.setdefault(normalized, []).append(entry)
    if len(paths) != 1:
        return None, [item.get("index") for item in entries]
    return entries[0], [item.get("index") for item in entries]


def _group_inventory(group: Any) -> dict[str, Any] | None:
    if not isinstance(group, dict):
        return None
    try:
        group_index = int(group.get("index"))
    except (TypeError, ValueError):
        group_index = None
    entries = _group_entries(group)
    rows: list[dict[str, Any]] = []
    for entry in entries[:_MAX_GROUP_INVENTORY_ENTRIES]:
        try:
            entry_index = int(entry.get("index"))
        except (TypeError, ValueError):
            entry_index = None
        names = entry.get("material_names") or []
        material_names = [
            str(name)
            for name in names
            if isinstance(name, str) and name.strip()
        ] if isinstance(names, (list, tuple)) else []
        path = str(entry.get("path") or "").strip()
        rows.append(
            {
                "index": entry_index,
                "material_names": material_names,
                "path": path or None,
                "path_kind": _entry_path_kind(path),
                "preview_color": _preview_rgb(entry.get("preview_color")),
            }
        )
    return {
        "group_index": group_index,
        "entry_count": len(entries),
        "entries_reported": len(rows),
        "entries_truncated": len(entries) > len(rows),
        "primary_group_preview_color": _preview_rgb(group.get("primary_group_preview_color")),
        "secondary_group_preview_color": _preview_rgb(group.get("secondary_group_preview_color")),
        "entries": rows,
    }


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
    """Diagnose the FH6 manufacturer swatch overlay boundary without rendering.

    Exact entry material-name matching remains the primary contract. ForzaTechStudio
    also treats ``carpaint`` and ``carpaint_secondary`` as built-in manufacturer
    color materials. For a multi-entry FH6 manufacturer group, those built-ins may
    resolve only through the group's native primary/secondary preview color when it
    identifies one entry, or multiple entries that all share one exact path. This
    preserves the group scheme semantics without guessing from mesh/path substrings.

    A candidate still requires an exact C_livery material binding, a resolved
    manufacturer group/entry path, and a valid native float VEC2 ``TEXCOORD_4``
    accessor whose vertex count matches POSITION. No UV coordinates are synthesized.
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
        "material_match_contract": "exact_entry_material_name_or_fts_builtin_group_preview_path",
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
        "builtin_unique_entry_match_count": 0,
        "builtin_primary_preview_match_count": 0,
        "builtin_secondary_preview_match_count": 0,
        "builtin_preview_same_path_match_count": 0,
        "missing_or_invalid_uv4_count": 0,
        "resolved_group_inventory": {},
        "candidates": [],
        "issues": list(record_issues),
        "interpretation_boundary": (
            "Paint P3D inventories manufacturer overlay candidates without rendering. Exact entry material-name "
            "matching is preferred. FTS built-in carpaint eligibility may use an FH6 group primary/secondary preview "
            "only when it resolves one entry or one shared exact path. It does not infer entries from mesh/path "
            "substrings, synthesize UV4, sample UV4, apply manufacturer tint/alpha, emulate finish shaders, or alter "
            "FH6 game/save data."
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
                "material_match_mode": None,
                "selector": None,
                "group_index": None,
                "entry_index": None,
                "matching_entry_indices": [],
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
                inventory = _group_inventory(group)
                if inventory is not None:
                    key = str(row["group_index"] if row["group_index"] is not None else selector)
                    report["resolved_group_inventory"].setdefault(key, inventory)

            if not material_name:
                report["missing_material_name_count"] += 1
                row["status"] = "kfps_material_name_missing"
                rows.append(row)
                continue

            matches = _exact_material_entry_matches(group, material_name)
            if len(matches) == 1:
                row["material_match_mode"] = "exact_entry_material_name"
            elif len(matches) > 1:
                report["ambiguous_entry_count"] += 1
                row["status"] = "manufacturer_entry_material_name_ambiguous"
                row["matching_entry_indices"] = [entry.get("index") for entry in matches]
                rows.append(row)
                continue
            else:
                group_entries = _group_entries(group)
                builtin_name = material_name.casefold()
                if builtin_name in _BUILTIN_MANUFACTURER_MATERIAL_NAMES and len(group_entries) == 1:
                    matches = [group_entries[0]]
                    row["material_match_mode"] = "fts_builtin_carpaint_unique_group_entry"
                    report["builtin_unique_entry_match_count"] += 1
                elif builtin_name in _BUILTIN_MANUFACTURER_MATERIAL_NAMES:
                    secondary = builtin_name == "carpaint_secondary"
                    preview_matches = _preview_entry_matches(group, secondary=secondary)
                    if len(preview_matches) == 1:
                        matches = preview_matches
                        row["material_match_mode"] = (
                            "fts_builtin_carpaint_secondary_preview_entry"
                            if secondary
                            else "fts_builtin_carpaint_primary_preview_entry"
                        )
                        if secondary:
                            report["builtin_secondary_preview_match_count"] += 1
                        else:
                            report["builtin_primary_preview_match_count"] += 1
                    elif len(preview_matches) > 1:
                        representative, matching_indices = _same_path_preview_match(preview_matches)
                        row["matching_entry_indices"] = matching_indices
                        if representative is None:
                            report["ambiguous_entry_count"] += 1
                            row["status"] = (
                                "manufacturer_entry_secondary_preview_ambiguous"
                                if secondary
                                else "manufacturer_entry_primary_preview_ambiguous"
                            )
                            rows.append(row)
                            continue
                        matches = [representative]
                        row["material_match_mode"] = (
                            "fts_builtin_carpaint_secondary_preview_same_path"
                            if secondary
                            else "fts_builtin_carpaint_primary_preview_same_path"
                        )
                        report["builtin_preview_same_path_match_count"] += 1
                        if secondary:
                            report["builtin_secondary_preview_match_count"] += 1
                        else:
                            report["builtin_primary_preview_match_count"] += 1
                    else:
                        report["unmatched_entry_count"] += 1
                        row["status"] = "manufacturer_entry_not_targeted_by_exact_material_name"
                        rows.append(row)
                        continue
                else:
                    report["unmatched_entry_count"] += 1
                    row["status"] = "manufacturer_entry_not_targeted_by_exact_material_name"
                    rows.append(row)
                    continue

            entry = matches[0]
            try:
                row["entry_index"] = int(entry.get("index"))
            except (TypeError, ValueError):
                row["entry_index"] = None
            if not row["matching_entry_indices"] and row["entry_index"] is not None:
                row["matching_entry_indices"] = [row["entry_index"]]
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
