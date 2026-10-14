from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from fh6garage.preview3d.native_bc5_normal_analysis import (
    NativeBc5NormalAnalysisError,
    analyze_bc5_unorm_normal_dds,
)
from fh6garage.preview3d.native_material_render_plan import (
    NativeMaterialRenderPlanError,
    build_native_material_render_plan,
)
from fh6garage.preview3d.native_normal_texture_diagnostics import (
    build_native_normal_texture_diagnostics,
)

_REPORT_FORMAT = "fh6_native_normal_bc5_validation_v1"


def _build_report(glb_path: str | Path) -> dict:
    glb = Path(glb_path).expanduser().resolve()
    plan = build_native_material_render_plan(glb)
    normal_report = build_native_normal_texture_diagnostics(plan)
    analyses: list[dict] = []
    for candidate in normal_report.candidates:
        if candidate.status != "bc5_decode_orientation_validation_required":
            continue
        try:
            analysis = analyze_bc5_unorm_normal_dds(candidate.dds_path)
            analyses.append(
                {
                    "mesh_index": candidate.mesh_index,
                    "mesh_name": candidate.mesh_name,
                    "mesh_role": candidate.mesh_role,
                    "material_name": candidate.material_name,
                    "parameter_hash": candidate.parameter_hash,
                    "parameter_name": candidate.parameter_name,
                    "texture_path": candidate.texture_path,
                    "dds_path": candidate.dds_path,
                    "status": "payload_hypothesis_evaluated",
                    "analysis": analysis.as_dict(),
                }
            )
        except NativeBc5NormalAnalysisError as exc:
            analyses.append(
                {
                    "mesh_index": candidate.mesh_index,
                    "mesh_name": candidate.mesh_name,
                    "mesh_role": candidate.mesh_role,
                    "material_name": candidate.material_name,
                    "parameter_hash": candidate.parameter_hash,
                    "parameter_name": candidate.parameter_name,
                    "texture_path": candidate.texture_path,
                    "dds_path": candidate.dds_path,
                    "status": "payload_analysis_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    return {
        "format": _REPORT_FORMAT,
        "glb_path": str(glb),
        "normal_texture_diagnostics": normal_report.as_dict(),
        "bc5_payload_analysis_count": len(analyses),
        "bc5_payload_analyses": analyses,
        "interpretation_boundary": (
            "R->X, G->Y and positive Z reconstruction are evaluated only as a standard "
            "BC5 tangent-normal hypothesis. FH6 Y orientation remains unproven."
        ),
        "rendering_enabled": False,
        "game_data_modified": False,
    }


def _write_atomic_json(path: Path, payload: dict, protected_paths: set[Path]) -> None:
    target = path.expanduser().resolve()
    if target in protected_paths:
        raise ValueError("Refusing to overwrite the GLB or any decoded DDS input with a diagnostic report.")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    temp = Path(temp_name)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as stream:
            stream.write(text)
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze verified native FH6 normal Texture2D candidates without enabling rendering."
        )
    )
    parser.add_argument("glb", help="Converted GLB with its .native_textures.json sidecar")
    parser.add_argument(
        "--output",
        help="Optional derivative JSON report path. If omitted, the report is printed to stdout.",
    )
    args = parser.parse_args()

    try:
        report = _build_report(args.glb)
    except (OSError, ValueError, NativeMaterialRenderPlanError) as exc:
        parser.error(f"{type(exc).__name__}: {exc}")

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        protected = {Path(args.glb).expanduser().resolve()}
        for item in report.get("bc5_payload_analyses", []):
            dds_path = str(item.get("dds_path") or "").strip()
            if dds_path:
                protected.add(Path(dds_path).expanduser().resolve())
        try:
            _write_atomic_json(Path(args.output), report, protected)
        except (OSError, ValueError) as exc:
            parser.error(f"{type(exc).__name__}: {exc}")
        print(str(Path(args.output).expanduser().resolve()))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
