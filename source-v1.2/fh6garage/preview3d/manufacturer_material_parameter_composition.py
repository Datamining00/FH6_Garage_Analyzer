from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .material_shader_parameter_helper import (
    MaterialShaderParameterHelperError,
    diagnose_material_shader_parameters,
)


MANUFACTURER_MATERIAL_PARAMETER_COMPOSITION_FORMAT = (
    "fh6_manufacturer_material_parameter_composition_v1"
)
MANUFACTURER_MATERIAL_PARAMETER_COMPOSITION_REVISION = 1


def _cache_path(mapping: Any) -> str | None:
    if not isinstance(mapping, dict):
        return None
    value = str(mapping.get("cache_path") or "").strip()
    return value or None


def _direct_exact_shader_pairs(node: Any):
    if not isinstance(node, dict):
        return

    material_cache = _cache_path(node.get("asset"))
    references = node.get("references")
    if isinstance(references, list):
        for attempt in references:
            if not isinstance(attempt, dict):
                continue
            if attempt.get("status") == "shader_resolved_exact" and material_cache:
                shader_cache = _cache_path(attempt.get("payload"))
                if shader_cache:
                    yield material_cache, shader_cache
            nested = attempt.get("nested")
            if isinstance(nested, dict):
                yield from _direct_exact_shader_pairs(nested)


def _unique_pairs(traced_report: Any) -> list[tuple[str, str]]:
    if not isinstance(traced_report, dict):
        return []
    traces = traced_report.get("traces")
    if not isinstance(traces, list):
        return []

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        for material_path, shader_path in _direct_exact_shader_pairs(trace.get("root")):
            key = (
                str(Path(material_path)).casefold(),
                str(Path(shader_path)).casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            pairs.append((material_path, shader_path))
    return pairs


def diagnose_manufacturer_material_parameter_composition(
    traced_report: Any,
    *,
    analyze_parameters: Callable[..., dict[str, Any]] = diagnose_material_shader_parameters,
) -> dict[str, Any]:
    """Decode each unique exact materialbin/shaderbin pair without rendering.

    Multiple paint primitives commonly resolve to the same material/shader pair;
    they are deliberately deduplicated so the external helper is invoked once per
    exact pair rather than once per mesh primitive.
    """
    report: dict[str, Any] = {
        "format": MANUFACTURER_MATERIAL_PARAMETER_COMPOSITION_FORMAT,
        "revision": MANUFACTURER_MATERIAL_PARAMETER_COMPOSITION_REVISION,
        "status": "manufacturer_material_shader_parameters_unavailable",
        "target_count": 0,
        "composed_count": 0,
        "failed_count": 0,
        "pairs": [],
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
        "composition_rule": (
            "key=NameHash|Type; first parameter per source; "
            "material override wins over linked shader default"
        ),
    }

    pairs = _unique_pairs(traced_report)
    report["target_count"] = len(pairs)
    if not pairs:
        report["status"] = "no_exact_material_shader_pair"
        return report

    rows: list[dict[str, Any]] = []
    for material_path, shader_path in pairs:
        row: dict[str, Any] = {
            "material_cache_path": material_path,
            "shader_cache_path": shader_path,
            "status": "material_shader_parameter_composition_failed",
        }
        try:
            helper = analyze_parameters(material_path, shader_path)
        except MaterialShaderParameterHelperError as exc:
            row["detail"] = str(exc)
            report["failed_count"] += 1
            rows.append(row)
            continue
        except Exception as exc:
            row["detail"] = f"{type(exc).__name__}: {exc}"
            report["failed_count"] += 1
            rows.append(row)
            continue

        row["helper"] = helper
        if isinstance(helper, dict) and helper.get("status") == "material_shader_parameters_composed":
            row["status"] = "material_shader_parameters_composed"
            report["composed_count"] += 1
        else:
            row["detail"] = str(
                helper.get("status") if isinstance(helper, dict) else "invalid_helper_report"
            )
            report["failed_count"] += 1
        rows.append(row)

    report["pairs"] = rows
    report["status"] = (
        "manufacturer_material_shader_parameters_diagnosed"
        if report["failed_count"] == 0 and report["composed_count"] == report["target_count"]
        else "manufacturer_material_shader_parameters_incomplete"
    )
    return report
