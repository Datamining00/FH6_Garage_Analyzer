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
    diagnostics["game_data_modified"] = False
    try:
        diagnostics["glb_size"] = int(output.stat().st_size)
    except OSError:
        pass
    _write_sidecar(output, diagnostics)
    return ConversionResult(str(output), diagnostics)
