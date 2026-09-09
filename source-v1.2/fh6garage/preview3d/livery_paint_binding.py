from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

from .manufacturer_colors import resolve_manufacturer_group_linear_paint
from .material_appearance_patch import _read_glb_document


LIVERY_PAINT_BINDING_REVISION = 3
# Pinned KFPS GlbWriter.cs emits MaterialBindingHash.ToString("X16"): exactly
# sixteen hexadecimal digits with no 0x prefix. Keep this parser identical to
# that exporter contract instead of accepting broader human-readable forms.
_CANONICAL_BINDING_HASH = re.compile(r"^([0-9A-Fa-f]{16})$")
_CUSTOM_COLOR_SELECTOR = 0xFFFFFFFF


def _canonical_binding_hash(value: Any) -> int | None:
    """Accept only the exact 16-digit X16 provenance emitted by KFPS."""
    if not isinstance(value, str):
        return None
    match = _CANONICAL_BINDING_HASH.fullmatch(value.strip())
    if match is None:
        return None
    return int(match.group(1), 16)


def _paint_record_index(report: Any) -> tuple[dict[int, dict[str, Any]], set[int], list[str]]:
    if not isinstance(report, dict) or report.get("status") != "paint_descriptor_parsed":
        return {}, set(), ["C_livery paint descriptor provenance is unavailable or unresolved."]

    unique: dict[int, dict[str, Any]] = {}
    ambiguous: set[int] = set()
    issues: list[str] = []
    for raw_record in report.get("records") or []:
        if not isinstance(raw_record, dict):
            issues.append("A paint descriptor record is not an object and was ignored.")
            continue
        try:
            material_hash = int(raw_record.get("material_identifier_u64_le"))
        except (TypeError, ValueError):
            issues.append("A paint descriptor record has no valid 64-bit material identifier.")
            continue
        if material_hash < 0 or material_hash > 0xFFFFFFFFFFFFFFFF:
            issues.append("A paint descriptor material identifier is outside the unsigned 64-bit range.")
            continue
        if material_hash in unique or material_hash in ambiguous:
            unique.pop(material_hash, None)
            ambiguous.add(material_hash)
            continue
        unique[material_hash] = raw_record
    if ambiguous:
        issues.append(
            "Duplicate C_livery material identifiers are ambiguous and were not rendered: "
            + ", ".join(f"0x{value:016X}" for value in sorted(ambiguous))
        )
    return unique, ambiguous, issues


def _record_primary_linear_rgb(
    record: dict[str, Any],
    manufacturer_colors: Any,
) -> tuple[np.ndarray | None, str, dict[str, Any] | None]:
    """Resolve only the exact P2 custom or P3B manufacturer primary color."""
    try:
        selector = int(record.get("manufacturer_color_selector"))
    except (TypeError, ValueError):
        return None, "manufacturer_selector_invalid", None

    # A manufacturer selector is itself a selected paint state. Do not gate this
    # branch on the custom primary-color enable bit: ForzaLiveryStudio explicitly
    # treats manufacturerSelector != 0xFFFFFFFF as selected paint independently
    # of primary.enabled/secondary.enabled.
    if selector != _CUSTOM_COLOR_SELECTOR:
        resolved = resolve_manufacturer_group_linear_paint(manufacturer_colors, selector)
        if resolved.get("status") != "manufacturer_primary_linear_resolved":
            return None, str(resolved.get("status") or "manufacturer_primary_unresolved"), resolved
        rgb = resolved.get("primary_linear_rgb")
        if not isinstance(rgb, (list, tuple)) or len(rgb) < 3:
            return None, "manufacturer_primary_trailer_invalid", resolved
        return np.asarray(rgb[:3], dtype=np.float32), "manufacturer_primary_ready", resolved

    if not bool(record.get("primary_color_enabled")):
        return None, "primary_color_disabled", None

    rgba = record.get("primary_rgba")
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 4:
        return None, "primary_rgba_invalid", None
    values: list[int] = []
    for component in rgba[:4]:
        if isinstance(component, bool):
            return None, "primary_rgba_invalid", None
        try:
            value = int(component)
        except (TypeError, ValueError):
            return None, "primary_rgba_invalid", None
        if value < 0 or value > 255:
            return None, "primary_rgba_invalid", None
        values.append(value)

    # The current PBR shader linearizes legacy/display paint colors with pow(2.2)
    # before the livery alpha composite. Use that exact established contract for
    # custom C_livery RGB. Manufacturer group trailer values are already linear
    # and therefore bypass this conversion above.
    display_rgb = np.asarray(values[:3], dtype=np.float32) / np.float32(255.0)
    return np.power(display_rgb, np.float32(2.2)).astype(np.float32), "custom_primary_ready", None


def _manufacturer_result_summary(material_hash: int, resolved: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_hash": f"0x{material_hash:016X}",
        "selector": resolved.get("selector"),
        "status": resolved.get("status"),
        "group_index": resolved.get("group_index"),
        "entry_count": resolved.get("entry_count"),
        "secondary_enabled": bool(resolved.get("secondary_enabled")),
        "secondary_status": resolved.get("secondary_status"),
    }


def apply_exact_livery_paint_to_aux_stream(
    glb_path: str | Path,
    scene_data: Any,
    aux_stream: np.ndarray,
    paint_provenance: Any,
    manufacturer_colors: Any = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply exact C_livery primary colors to the existing PBR aux stream.

    Paint binding has no mesh-name, filename, material-name, panel, or
    vehicle-specific fallback. A GLB primitive must declare role=paint and carry
    the exact unprefixed 16-digit `kfps_material_binding_hash` emitted by pinned
    KFPS GlbWriter.cs; that 64-bit value must match one unique C_livery paint
    record.

    P2 custom paint consumes the enabled custom BGRA primary. P3B additionally
    accepts a non-FFFFFFFF manufacturer selector and resolves it only to the FH6
    ManufacturerColors group trailer primary RGB. The trailer RGB is kept linear
    for the existing linear PBR aux stream. Entry-specific material paths, UV4
    overlays, secondary/two-tone mixing, flake, and finish materials remain
    deferred.
    """
    if not isinstance(aux_stream, np.ndarray) or aux_stream.ndim != 2 or aux_stream.shape[1] != 4:
        raise ValueError("Paint binding requires an Nx4 material aux stream.")
    expected_vertices = int(len(getattr(scene_data, "positions")))
    if len(aux_stream) != expected_vertices:
        raise ValueError(
            f"Paint aux stream vertex count {len(aux_stream)} does not match scene {expected_vertices}."
        )

    records, ambiguous_hashes, record_issues = _paint_record_index(paint_provenance)
    output = np.ascontiguousarray(aux_stream.copy(), dtype=np.float32)
    report: dict[str, Any] = {
        "format": "fh6_livery_paint_binding_v1",
        "binding_revision": LIVERY_PAINT_BINDING_REVISION,
        "binding_format": "kfps_material_binding_hash_x16_unprefixed",
        "status": "paint_binding_unavailable" if not records and not ambiguous_hashes else "paint_binding_evaluated",
        "rendering_applied": False,
        "game_data_modified": False,
        "matched_primitives": 0,
        "matched_vertices": 0,
        "matched_custom_primitives": 0,
        "matched_manufacturer_primitives": 0,
        "exact_record_count": len(records),
        "ambiguous_record_count": len(ambiguous_hashes),
        "manufacturer_matched_hashes": [],
        "deferred_manufacturer_hashes": [],
        "manufacturer_selector_results": [],
        "disabled_primary_hashes": [],
        "unmatched_paint_hashes": [],
        "malformed_binding_primitives": [],
        "issues": list(record_issues),
        "interpretation_boundary": (
            "Paint P3B applies only unique exact-hash custom primaries and resolved FH6 manufacturer group-trailer "
            "primary colors. Secondary/two-tone mixing, entry Path/material targeting, UV4 overlays, flake, finish "
            "materials, and paint-group inheritance remain deferred."
        ),
    }
    if not isinstance(paint_provenance, dict) or paint_provenance.get("status") != "paint_descriptor_parsed":
        return output, report

    document = _read_glb_document(Path(glb_path))
    meshes = document.get("meshes") or []
    accessors = document.get("accessors") or []
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

    offset = 0
    unmatched: set[int] = set()
    matched_manufacturer: set[int] = set()
    deferred_manufacturer: set[int] = set()
    disabled_primary: set[int] = set()
    manufacturer_results: dict[int, dict[str, Any]] = {}
    for diagnostic_index, diagnostic in enumerate(
        tuple(getattr(scene_data, "primitive_diagnostics", ()) or ())
    ):
        mesh_index = int(diagnostic.get("mesh_index", -1))
        primitive_index = int(diagnostic.get("primitive_index", -1))
        if mesh_index < 0 or mesh_index >= len(meshes):
            raise ValueError("Paint binding mesh index is outside the GLB.")
        mesh = meshes[mesh_index]
        primitives = mesh.get("primitives") or []
        if primitive_index < 0 or primitive_index >= len(primitives):
            raise ValueError("Paint binding primitive index is outside the GLB.")
        attrs = primitives[primitive_index].get("attributes") or {}
        accessor_index = int(attrs["POSITION"])
        if accessor_index < 0 or accessor_index >= len(accessors):
            raise ValueError("Paint binding POSITION accessor is outside the GLB.")
        vertex_count = int(accessors[accessor_index].get("count", 0))
        if vertex_count <= 0:
            raise ValueError("Paint binding primitive has no vertices.")
        end = offset + vertex_count
        if end > len(output):
            raise ValueError("Paint binding primitive ranges exceed the material aux stream.")

        extras = dict(node_extras_by_mesh.get(mesh_index) or {})
        extras.update(mesh.get("extras") or {})
        role = str(diagnostic.get("declared_role") or extras.get("kfps_role") or "trim").casefold()
        if role == "paint":
            binding_hash = _canonical_binding_hash(extras.get("kfps_material_binding_hash"))
            if binding_hash is None:
                report["malformed_binding_primitives"].append(
                    {"diagnostic_index": diagnostic_index, "mesh_index": mesh_index, "primitive_index": primitive_index}
                )
            elif binding_hash in ambiguous_hashes:
                pass
            else:
                record = records.get(binding_hash)
                if record is None:
                    unmatched.add(binding_hash)
                else:
                    linear_rgb, state, manufacturer_result = _record_primary_linear_rgb(
                        record,
                        manufacturer_colors,
                    )
                    if manufacturer_result is not None:
                        manufacturer_results[binding_hash] = _manufacturer_result_summary(
                            binding_hash,
                            manufacturer_result,
                        )
                    if linear_rgb is not None:
                        output[offset:end, 1:4] = linear_rgb[None, :]
                        report["matched_primitives"] += 1
                        report["matched_vertices"] += vertex_count
                        if state == "manufacturer_primary_ready":
                            report["matched_manufacturer_primitives"] += 1
                            matched_manufacturer.add(binding_hash)
                        else:
                            report["matched_custom_primitives"] += 1
                    elif manufacturer_result is not None:
                        deferred_manufacturer.add(binding_hash)
                    elif state == "primary_color_disabled":
                        disabled_primary.add(binding_hash)
                    else:
                        report["issues"].append(
                            f"0x{binding_hash:016X} primary paint is invalid ({state}) and was not rendered."
                        )
        offset = end

    if offset != len(output):
        raise ValueError(
            f"Paint binding flattened primitive vertex count {offset} does not match aux stream {len(output)}."
        )

    report["manufacturer_matched_hashes"] = [
        f"0x{value:016X}" for value in sorted(matched_manufacturer)
    ]
    report["deferred_manufacturer_hashes"] = [
        f"0x{value:016X}" for value in sorted(deferred_manufacturer)
    ]
    report["manufacturer_selector_results"] = [
        manufacturer_results[value] for value in sorted(manufacturer_results)
    ]
    report["disabled_primary_hashes"] = [
        f"0x{value:016X}" for value in sorted(disabled_primary)
    ]
    report["unmatched_paint_hashes"] = [f"0x{value:016X}" for value in sorted(unmatched)]
    report["rendering_applied"] = report["matched_primitives"] > 0
    if report["rendering_applied"]:
        if report["matched_manufacturer_primitives"] and report["matched_custom_primitives"]:
            report["status"] = "exact_primary_paint_applied"
        elif report["matched_manufacturer_primitives"]:
            report["status"] = "exact_manufacturer_primary_applied"
        else:
            report["status"] = "exact_custom_primary_applied"
    else:
        report["status"] = "no_exact_primary_paint_applied"
    return output, report
