from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .manufacturer_colors import CUSTOM_COLOR_SELECTOR, resolve_manufacturer_selector


LIVERY_PAINT_SECONDARY_DIAGNOSTICS_FORMAT = "fh6_livery_paint_secondary_diagnostics_v1"
LIVERY_PAINT_SECONDARY_DIAGNOSTICS_REVISION = 1


def _u64(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 0xFFFFFFFFFFFFFFFF else None


def _u32(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 0xFFFFFFFF else None


def _rgba(value: Any) -> list[int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    output: list[int] = []
    for component in value[:4]:
        if isinstance(component, bool):
            return None
        try:
            parsed = int(component)
        except (TypeError, ValueError):
            return None
        if parsed < 0 or parsed > 255:
            return None
        output.append(parsed)
    return output


def _display_rgba_to_linear_rgb(rgba: list[int]) -> list[float]:
    return [float((component / 255.0) ** 2.2) for component in rgba[:3]]


def _linear_rgb(value: Any) -> list[float] | None:
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
        output.append(max(0.0, min(1.0, number)))
    return output


def _manufacturer_secondary(report: Any, selector: int) -> dict[str, Any]:
    resolved = resolve_manufacturer_selector(report, selector)
    result: dict[str, Any] = {
        "status": resolved.get("status"),
        "selector": resolved.get("selector"),
        "group_index": None,
        "entry_count": 0,
        "secondary_enabled": False,
        "secondary_linear_rgb": None,
    }
    if resolved.get("status") != "manufacturer_group_resolved":
        return result

    group = resolved.get("group")
    if not isinstance(group, dict):
        result["status"] = "manufacturer_group_invalid"
        return result
    try:
        result["group_index"] = int(group.get("index"))
        result["entry_count"] = int(group.get("entry_count", len(group.get("entries") or [])))
    except (TypeError, ValueError):
        result["status"] = "manufacturer_group_invalid"
        return result

    if not bool(group.get("secondary_group_preview_present")):
        result["status"] = "manufacturer_secondary_not_present"
        return result
    secondary = _linear_rgb(group.get("secondary_group_preview_color"))
    if secondary is None:
        result["status"] = "manufacturer_secondary_trailer_invalid"
        return result
    result["status"] = "manufacturer_secondary_linear_preserved"
    result["secondary_enabled"] = True
    result["secondary_linear_rgb"] = secondary
    return result


def build_livery_paint_secondary_diagnostics(
    paint_provenance: Any,
    manufacturer_colors: Any = None,
) -> dict[str, Any]:
    """Preserve secondary/finish provenance without enabling two-tone rendering.

    Public ForzaLiveryStudio evidence establishes only the ordering needed here:
    a resolved manufacturer secondary is assigned first, then an enabled C_livery
    secondary overrides it. The later secondary mix is finish/material dependent,
    and FLS explicitly labels its hardcoded fallback as an approximation. P3C
    therefore records the exact available secondary source and raw finish code but
    does not choose a mix factor, flake model, finish shader, material entry path,
    or UV channel.
    """
    report: dict[str, Any] = {
        "format": LIVERY_PAINT_SECONDARY_DIAGNOSTICS_FORMAT,
        "revision": LIVERY_PAINT_SECONDARY_DIAGNOSTICS_REVISION,
        "status": "secondary_finish_provenance_unavailable",
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
        "record_count": 0,
        "duplicate_material_identifiers": [],
        "records": [],
        "issues": [],
        "interpretation_boundary": (
            "Paint P3C diagnoses custom/manufacturer secondary-color precedence and preserves raw finish codes only. "
            "No secondary mixing, two-tone/flake shading, finish-code semantic mapping, entry Path/material targeting, "
            "or UV4 overlay is enabled until an FH6 engine-equivalent contract is proven."
        ),
    }
    if not isinstance(paint_provenance, dict) or paint_provenance.get("status") != "paint_descriptor_parsed":
        report["issues"].append("C_livery paint descriptor provenance is unavailable or unresolved.")
        return report

    records = [record for record in (paint_provenance.get("records") or []) if isinstance(record, dict)]
    material_values = [_u64(record.get("material_identifier_u64_le")) for record in records]
    counts = Counter(value for value in material_values if value is not None)
    duplicates = sorted(value for value, count in counts.items() if count > 1)
    report["duplicate_material_identifiers"] = [f"0x{value:016X}" for value in duplicates]

    output_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        material_hash = _u64(record.get("material_identifier_u64_le"))
        selector = _u32(record.get("manufacturer_color_selector"))
        finish_code = _u32(record.get("finish_code"))
        custom_enabled = bool(record.get("secondary_color_enabled"))
        custom_rgba = _rgba(record.get("secondary_rgba")) if custom_enabled else None

        manufacturer = None
        if selector is not None and selector != CUSTOM_COLOR_SELECTOR:
            manufacturer = _manufacturer_secondary(manufacturer_colors, selector)

        secondary_source = "none"
        secondary_status = "secondary_not_selected"
        selected_linear_rgb: list[float] | None = None
        if custom_enabled:
            if custom_rgba is None:
                secondary_source = "custom_secondary_override"
                secondary_status = "custom_secondary_invalid_deferred"
            else:
                secondary_source = "custom_secondary_override"
                secondary_status = "custom_secondary_preserved_deferred"
                selected_linear_rgb = _display_rgba_to_linear_rgb(custom_rgba)
        elif manufacturer is not None:
            if manufacturer.get("status") == "manufacturer_secondary_linear_preserved":
                secondary_source = "manufacturer_group_trailer"
                secondary_status = "manufacturer_secondary_preserved_deferred"
                selected_linear_rgb = list(manufacturer.get("secondary_linear_rgb") or [])
            else:
                secondary_source = "manufacturer_group_trailer"
                secondary_status = str(manufacturer.get("status") or "manufacturer_secondary_unresolved")

        output_records.append(
            {
                "record_index": index,
                "material_hash": f"0x{material_hash:016X}" if material_hash is not None else None,
                "binding_status": (
                    "ambiguous_duplicate_material_identifier"
                    if material_hash in duplicates
                    else "exact_material_identifier"
                    if material_hash is not None
                    else "material_identifier_invalid"
                ),
                "manufacturer_selector": selector,
                "manufacturer_secondary": manufacturer,
                "custom_secondary_enabled": custom_enabled,
                "custom_secondary_rgba": custom_rgba,
                "secondary_source_precedence": secondary_source,
                "secondary_status": secondary_status,
                "secondary_linear_rgb_candidate": selected_linear_rgb,
                "finish_code_raw": finish_code,
                "finish_status": (
                    "raw_finish_code_preserved_deferred" if finish_code is not None else "finish_code_invalid_deferred"
                ),
                "mixing_status": "secondary_mix_and_finish_shader_deferred",
                "rendering_enabled": False,
            }
        )

    report["record_count"] = len(output_records)
    report["records"] = output_records
    report["status"] = "secondary_finish_provenance_diagnosed"
    if len(output_records) != len(paint_provenance.get("records") or []):
        report["issues"].append("Non-object paint descriptor records were ignored during P3C diagnostics.")
    if duplicates:
        report["issues"].append(
            "Duplicate material identifiers remain binding-ambiguous; P3C does not choose one record for rendering."
        )
    return report
