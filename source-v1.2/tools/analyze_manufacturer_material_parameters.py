from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Direct execution from source-v1.2/tools sets sys.path[0] to this tools directory,
# not the source-v1.2 package root. Keep the diagnostic runnable both as a
# source script and as a PyInstaller entry point without requiring PYTHONPATH.
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from fh6garage.preview3d.manufacturer_material_parameter_composition import (
    diagnose_manufacturer_material_parameter_composition,
)
from fh6garage.preview3d.wheel_morph_helper import (
    WHEEL_MORPH_HELPER_REVISION,
    WHEEL_MORPH_HELPER_SHA256,
    WheelMorphHelperError,
    verified_bundled_wheel_morph_helper,
)


CLI_FORMAT = "fh6_manufacturer_material_parameter_cli_v1"
CLI_REVISION = 1
P3F_FORMAT = "fh6_manufacturer_materialbin_diagnostics_v1"


def _default_output(source: Path) -> Path:
    stem = source.stem
    if stem.lower().endswith("_manufacturer_materialbin_p3f"):
        stem = stem[: -len("_manufacturer_materialbin_p3f")]
    return source.with_name(f"{stem}_material_shader_parameters.json")


def _base_report(status: str) -> dict[str, Any]:
    return {
        "cli_format": CLI_FORMAT,
        "cli_revision": CLI_REVISION,
        "status": status,
        "helper_revision": WHEEL_MORPH_HELPER_REVISION,
        "helper_sha256": WHEEL_MORPH_HELPER_SHA256,
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
    }


def _write_json(output: Path | None, report: dict[str, Any]) -> None:
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")
    print(text)


def _self_check() -> int:
    report = _base_report("material_shader_parameter_self_check_failed")
    try:
        helper = verified_bundled_wheel_morph_helper()
    except WheelMorphHelperError as exc:
        report["detail"] = str(exc)
        _write_json(None, report)
        return 5
    if helper is None:
        report["detail"] = "The SHA-verified bundled KFPS helper is unavailable."
        _write_json(None, report)
        return 5
    report["status"] = "material_shader_parameter_self_check_passed"
    report["verified_helper"] = str(helper)
    _write_json(None, report)
    return 0


def run(p3f_path: Path, output_path: Path | None) -> int:
    source = p3f_path.expanduser().resolve()
    if not source.is_file():
        report = _base_report("material_shader_parameter_input_failed")
        report["detail"] = f"P3F JSON does not exist: {source}"
        _write_json(output_path, report)
        return 2

    output = (output_path or _default_output(source)).expanduser().resolve()
    if output == source:
        report = _base_report("material_shader_parameter_output_rejected")
        report["detail"] = "Refusing to overwrite the source P3F JSON."
        _write_json(None, report)
        return 3

    try:
        p3f = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        report = _base_report("material_shader_parameter_input_failed")
        report["detail"] = f"P3F JSON could not be read: {type(exc).__name__}: {exc}"
        report["p3f_source"] = str(source)
        _write_json(output, report)
        return 2

    if not isinstance(p3f, dict) or p3f.get("format") != P3F_FORMAT:
        report = _base_report("material_shader_parameter_input_failed")
        report["detail"] = "Input is not an FH6 manufacturer materialbin P3F diagnostic JSON."
        report["p3f_source"] = str(source)
        _write_json(output, report)
        return 2
    if p3f.get("game_data_modified") is not False:
        report = _base_report("material_shader_parameter_input_failed")
        report["detail"] = "P3F input does not explicitly preserve game_data_modified=false."
        report["p3f_source"] = str(source)
        _write_json(output, report)
        return 2
    if int(p3f.get("exact_shader_resolved_count") or 0) <= 0:
        report = _base_report("material_shader_parameter_input_failed")
        report["detail"] = (
            "P3F input contains no exact shader-resolved material chain. "
            "Run the current P3F diagnostic first."
        )
        report["p3f_source"] = str(source)
        _write_json(output, report)
        return 2

    composition = diagnose_manufacturer_material_parameter_composition(p3f)
    report = _base_report("manufacturer_material_shader_parameter_diagnostic_failed")
    report["p3f_source"] = str(source)
    report["p3f_revision"] = p3f.get("revision")
    report["p3f_validation_status"] = p3f.get("validation_status")
    report["p3f_candidate_count"] = p3f.get("candidate_count")
    report["p3f_exact_shader_resolved_count"] = p3f.get("exact_shader_resolved_count")
    report["parameter_composition"] = composition

    target_count = int(composition.get("target_count") or 0)
    composed_count = int(composition.get("composed_count") or 0)
    failed_count = int(composition.get("failed_count") or 0)
    if target_count > 0 and composed_count == target_count and failed_count == 0:
        report["status"] = "manufacturer_material_shader_parameter_diagnostic_passed"
        _write_json(output, report)
        return 0

    if target_count == 0:
        report["detail"] = (
            "No exact cached materialbin/shaderbin pair was present in the P3F trace. "
            "Run the current P3F diagnostic again so exact cache paths are recorded."
        )
    else:
        report["detail"] = (
            f"Parameter composition incomplete: {composed_count}/{target_count} pairs composed; "
            f"{failed_count} failed."
        )
    _write_json(output, report)
    return 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read an FH6 P3F diagnostic JSON and compose exact materialbin overrides with "
            "linked shaderbin defaults. This diagnostic is read-only and does not render."
        )
    )
    parser.add_argument("--p3f", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)

    if args.self_check:
        return _self_check()
    if args.p3f is None:
        parser.error("--p3f is required unless --self-check is used")
    return run(args.p3f, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
