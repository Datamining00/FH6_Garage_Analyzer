from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Callable

from .converter_base import (
    ChassisConverterError,
    ConversionResult,
    app_data_root,
    cache_dir,
    converter_is_valid,
    converter_path,
    ensure_converter,
)
from .converter_base import convert_vehicle as _convert_vehicle_base
from .material_inventory import MATERIAL_INVENTORY_REVISION, build_material_inventory
from .vehicle_assets import VehicleAsset
from .wheel_visibility import (
    WHEEL_VISIBILITY_REVISION,
    WheelVisibilityError,
    apply_neutral_wheel_visibility,
)


def _write_sidecar(output: Path, diagnostics: dict) -> None:
    output.with_suffix(".json").write_text(
        json.dumps(diagnostics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _material_inventory_summary(report) -> dict:
    return {
        "source_name": report.source_name,
        "asset_generator": report.asset_generator,
        "scene_format": report.scene_format,
        "mesh_count": int(report.mesh_count),
        "node_count": int(report.node_count),
        "gltf_material_count": int(report.gltf_material_count),
        "primitive_material_references": int(report.primitive_material_references),
        "resolved_binding_hashes": int(report.resolved_binding_hashes),
        "zero_binding_hashes": int(report.zero_binding_hashes),
        "missing_binding_hashes": int(report.missing_binding_hashes),
        "malformed_binding_hashes": int(report.malformed_binding_hashes),
        "extras_mismatch_meshes": int(report.extras_mismatch_meshes),
        "game_data_modified": bool(report.game_data_modified),
    }


def convert_vehicle(
    asset: VehicleAsset,
    progress: Callable[[str], None] | None = None,
    *,
    carbin_entry: str,
) -> ConversionResult:
    """Run the validated packaged converter, then apply FinalVerify1 ErrorFix1.

    WheelStyle visibility is post-processing of the LocalAppData-derived GLB. A
    structural ordered-mapping validation failure must never invalidate a GLB
    that the chassis converter and neutral-geometry classifier already accepted.
    Material inventory is diagnostics-only and follows the same fail-open rule:
    inability to inspect KFPS metadata must not invalidate valid geometry.
    """
    result = _convert_vehicle_base(
        asset,
        progress=progress,
        carbin_entry=carbin_entry,
    )
    output = Path(result.output_path)
    diagnostics = dict(result.diagnostics or {})
    wheel_visibility_summary: dict = {}
    wheel_visibility_error: str | None = None

    try:
        wheel_visibility_summary = apply_neutral_wheel_visibility(
            output,
            Path(asset.archive_path),
        ).as_dict()
    except (OSError, ValueError, zipfile.BadZipFile, WheelVisibilityError) as exc:
        wheel_visibility_error = f"{type(exc).__name__}: {exc}"

    if wheel_visibility_error:
        # ErrorFix1: WheelStyle visibility is a derived-GLB post-processing aid,
        # not a prerequisite for a valid chassis conversion. Some vehicles do
        # not satisfy the ordered modelbin/GLB index-count join even though the
        # converter produced a valid GLB. Preserve that GLB and record the
        # validation failure instead of deleting or rejecting the output.
        wheel_visibility_summary = dict(wheel_visibility_summary or {})
        wheel_visibility_summary.setdefault("status", "validation_failed_proceeding")

    diagnostics["wheel_visibility_revision"] = WHEEL_VISIBILITY_REVISION
    diagnostics["wheel_visibility_status"] = (
        wheel_visibility_summary.get("status", "failed")
        if wheel_visibility_summary
        else "failed"
    )
    diagnostics["wheel_visibility"] = wheel_visibility_summary
    diagnostics["wheel_visibility_error"] = wheel_visibility_error

    material_inventory_summary: dict = {}
    material_inventory_error: str | None = None
    try:
        material_inventory_summary = _material_inventory_summary(
            build_material_inventory(output)
        )
    except Exception as exc:
        # Diagnostics-only boundary. A parser/metadata problem must never make a
        # converter-validated GLB unusable or interfere with ErrorFix1.
        material_inventory_error = f"{type(exc).__name__}: {exc}"

    diagnostics["material_inventory_revision"] = MATERIAL_INVENTORY_REVISION
    diagnostics["material_inventory_status"] = (
        "ok" if material_inventory_error is None else "failed_proceeding"
    )
    diagnostics["material_inventory"] = material_inventory_summary
    diagnostics["material_inventory_error"] = material_inventory_error
    diagnostics["game_data_modified"] = False
    try:
        diagnostics["glb_size"] = int(output.stat().st_size)
    except OSError:
        pass
    _write_sidecar(output, diagnostics)
    return ConversionResult(str(output), diagnostics)
