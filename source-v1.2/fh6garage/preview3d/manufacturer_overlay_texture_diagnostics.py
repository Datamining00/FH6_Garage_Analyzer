from __future__ import annotations

from pathlib import Path
from typing import Any

from .manufacturer_overlay_diagnostics import diagnose_manufacturer_overlay
from .native_material_textures import resolve_native_texture_reference


MANUFACTURER_OVERLAY_TEXTURE_DIAGNOSTICS_FORMAT = "fh6_manufacturer_overlay_texture_diagnostics_v1"
MANUFACTURER_OVERLAY_TEXTURE_DIAGNOSTICS_REVISION = 1

# These modes preserve the referenced path through a structurally exact lookup.
# The generic native resolver also has a unique-filename textures.zip fallback;
# P3E records that fallback but deliberately does not promote it to an exact
# manufacturer-overlay payload contract.
_EXACT_RESOLUTION_MODES = frozenset(
    {
        "vehicle_archive_exact",
        "game_loose_exact",
        "derived_zip_exact",
    }
)


def resolve_manufacturer_overlay_payloads(
    p3d_report: Any,
    vehicle_archive: str | Path,
    cache_root: str | Path,
) -> dict[str, Any]:
    """Resolve direct P3D swatchbin candidates without enabling UV4 rendering.

    Only rows already proven by P3D as exact binding/material-name/UV4 candidates
    are eligible. Their exact ManufacturerColorEntry Path is passed unchanged to
    the established native Texture2D resolver. Only structurally exact resolution
    modes are promoted; a unique-filename fallback is preserved diagnostically but
    remains deferred. No DDS decode, texture upload, UV sampling, tint composition,
    or game/save write is performed by this stage.
    """
    report: dict[str, Any] = {
        "format": MANUFACTURER_OVERLAY_TEXTURE_DIAGNOSTICS_FORMAT,
        "revision": MANUFACTURER_OVERLAY_TEXTURE_DIAGNOSTICS_REVISION,
        "status": "manufacturer_overlay_texture_diagnostics_unavailable",
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
        "candidate_count": 0,
        "exact_resolved_count": 0,
        "fallback_deferred_count": 0,
        "unresolved_count": 0,
        "payloads": [],
        "issues": [],
        "interpretation_boundary": (
            "Paint P3E resolves only direct .swatchbin payload bytes for P3D-exact manufacturer overlay candidates. "
            "Only vehicle_archive_exact, game_loose_exact, and derived_zip_exact resolution modes are promoted. "
            "Unique-filename fallback, .materialbin traversal, DDS decode/detile, UV4 sampling, tint/alpha composition, "
            "finish shaders, and rendering remain deferred. FH6 game/save data is never modified."
        ),
    }
    if not isinstance(p3d_report, dict) or p3d_report.get("status") != "manufacturer_overlay_candidates_diagnosed":
        report["issues"].append("P3D manufacturer overlay diagnostics are unavailable or unresolved.")
        return report

    rows = p3d_report.get("candidates") or []
    if not isinstance(rows, list):
        report["issues"].append("P3D candidate inventory is malformed.")
        return report

    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "exact_manufacturer_overlay_candidate_diagnosed":
            continue
        entry_path = str(row.get("entry_path") or "").strip()
        if not entry_path:
            continue

        report["candidate_count"] += 1
        payload = resolve_native_texture_reference(entry_path, vehicle_archive, cache_root)
        payload_dict = payload.as_dict()
        resolution_mode = str(payload.resolution_mode or "")
        resolution_status = str(payload.status or "")

        if resolution_status == "resolved_payload" and resolution_mode in _EXACT_RESOLUTION_MODES:
            p3e_status = "manufacturer_overlay_payload_resolved_exact"
            report["exact_resolved_count"] += 1
        elif resolution_status == "resolved_payload":
            p3e_status = "manufacturer_overlay_payload_fallback_deferred"
            report["fallback_deferred_count"] += 1
        else:
            p3e_status = "manufacturer_overlay_payload_unresolved"
            report["unresolved_count"] += 1

        output.append(
            {
                "mesh_index": row.get("mesh_index"),
                "primitive_index": row.get("primitive_index"),
                "material_hash": row.get("material_hash"),
                "material_name": row.get("material_name"),
                "selector": row.get("selector"),
                "group_index": row.get("group_index"),
                "entry_index": row.get("entry_index"),
                "entry_path": entry_path,
                "uv4_status": (row.get("uv4") or {}).get("status") if isinstance(row.get("uv4"), dict) else None,
                "status": p3e_status,
                "exact_resolution_approved": p3e_status == "manufacturer_overlay_payload_resolved_exact",
                "payload": payload_dict,
                "rendering_enabled": False,
            }
        )

    report["payloads"] = output
    report["status"] = "manufacturer_overlay_texture_payloads_diagnosed"
    return report


def diagnose_manufacturer_overlay_texture_payloads(
    glb_path: str | Path,
    paint_source: str | Path,
    vehicle_archive: str | Path,
    cache_root: str | Path,
) -> dict[str, Any]:
    """Run P3D then resolve its direct swatchbin candidates through P3E."""
    p3d_report = diagnose_manufacturer_overlay(glb_path, paint_source, vehicle_archive)
    result = resolve_manufacturer_overlay_payloads(p3d_report, vehicle_archive, cache_root)
    result = dict(result)
    result["p3d_status"] = p3d_report.get("status")
    result["p3d_exact_candidate_count"] = p3d_report.get("exact_candidate_count")
    result["glb_file"] = str(Path(glb_path))
    result["paint_source"] = str(Path(paint_source))
    result["vehicle_archive"] = str(Path(vehicle_archive))
    result["cache_root"] = str(Path(cache_root))
    return result
