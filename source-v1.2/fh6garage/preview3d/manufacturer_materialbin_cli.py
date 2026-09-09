from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .manufacturer_materialbin_diagnostics import trace_manufacturer_materialbin_payloads
from .manufacturer_overlay_diagnostics import diagnose_manufacturer_overlay
from .wheel_morph_helper import (
    WHEEL_MORPH_HELPER_REVISION,
    WHEEL_MORPH_HELPER_SHA256,
    WheelMorphHelperError,
    verified_bundled_wheel_morph_helper,
)


MANUFACTURER_MATERIALBIN_CLI_FORMAT = "fh6_manufacturer_materialbin_cli_v1"
MANUFACTURER_MATERIALBIN_CLI_REVISION = 1


def _existing_file(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Input file does not exist: {path}")
    return path


def _validation_status(report: dict) -> str:
    if report.get("status") != "manufacturer_materialbin_payloads_diagnosed":
        return "diagnostic_unavailable"
    if int(report.get("exact_resolved_count") or 0) > 0:
        return "exact_swatch_chain_resolved"
    if int(report.get("candidate_count") or 0) == 0:
        return "no_materialbin_candidate"
    if int(report.get("blocked_count") or 0) > 0:
        return "materialbin_chain_blocked"
    return "materialbin_chain_unresolved"


def _emit_error(message: str) -> None:
    stream = getattr(sys, "stderr", None)
    if stream is not None:
        print(message, file=stream)


def _write_result(result: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    stream = getattr(sys, "stdout", None)
    if stream is not None:
        print(payload, file=stream)


def _base_cli_report(status: str) -> dict[str, Any]:
    return {
        "cli_format": MANUFACTURER_MATERIALBIN_CLI_FORMAT,
        "cli_revision": MANUFACTURER_MATERIALBIN_CLI_REVISION,
        "status": status,
        "helper_revision": WHEEL_MORPH_HELPER_REVISION,
        "helper_sha256": WHEEL_MORPH_HELPER_SHA256,
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Paint P3F diagnostic: follow P3D-exact manufacturer .materialbin entries "
            "through exact MatL/Texture2D references to the first exact swatchbin."
        )
    )
    parser.add_argument("--self-check", action="store_true", help="Verify the packaged P3F module/helper contract only")
    parser.add_argument("--glb", type=_existing_file)
    parser.add_argument("--paint", type=_existing_file, help="C_livery paint source")
    parser.add_argument("--vehicle", type=_existing_file, help="Selected FH6 vehicle ZIP")
    parser.add_argument("--cache", type=Path, help="Writable diagnostic cache root outside FH6 data")
    parser.add_argument("--output", type=Path, help="Optional diagnostic JSON output path")
    return parser


def _run_self_check(output: Path | None) -> int:
    result = _base_cli_report("packaged_p3f_self_check_failed")
    result["validation_status"] = "packaged_contract_unavailable"
    try:
        helper = verified_bundled_wheel_morph_helper()
    except WheelMorphHelperError as exc:
        result["detail"] = str(exc)
        _write_result(result, output)
        return 4
    if helper is None:
        result["detail"] = "The SHA-verified bundled KFPS helper is unavailable."
        _write_result(result, output)
        return 4
    result["status"] = "packaged_p3f_self_check_passed"
    result["validation_status"] = "packaged_contract_ready"
    result["verified_helper"] = str(helper)
    _write_result(result, output)
    return 0


def run_manufacturer_materialbin_diagnostic(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    output = args.output.expanduser().resolve() if args.output is not None else None

    if args.self_check:
        return _run_self_check(output)

    if args.glb is None or args.paint is None or args.vehicle is None or args.cache is None:
        _emit_error("--glb, --paint, --vehicle, and --cache are required unless --self-check is used.")
        return 2

    cache = args.cache.expanduser().resolve()
    protected_inputs = {args.glb, args.paint, args.vehicle}
    if output is not None and output in protected_inputs:
        _emit_error("Refusing to overwrite a diagnostic source input with JSON output.")
        return 2
    if cache in protected_inputs:
        _emit_error("Refusing to use a diagnostic source file as the cache root.")
        return 2

    try:
        p3d = diagnose_manufacturer_overlay(args.glb, args.paint, args.vehicle)
        traced = trace_manufacturer_materialbin_payloads(p3d, args.vehicle, cache)
    except Exception as exc:
        result = _base_cli_report("manufacturer_materialbin_diagnostic_failed")
        result["validation_status"] = "diagnostic_execution_failed"
        result["detail"] = f"{type(exc).__name__}: {exc}"
        result["glb_file"] = str(args.glb)
        result["paint_source"] = str(args.paint)
        result["vehicle_archive"] = str(args.vehicle)
        result["cache_root"] = str(cache)
        _write_result(result, output)
        return 5

    result = dict(traced)
    result["cli_format"] = MANUFACTURER_MATERIALBIN_CLI_FORMAT
    result["cli_revision"] = MANUFACTURER_MATERIALBIN_CLI_REVISION
    result["validation_status"] = _validation_status(result)
    result["p3d_status"] = p3d.get("status")
    result["p3d_exact_candidate_count"] = p3d.get("exact_candidate_count")
    result["glb_file"] = str(args.glb)
    result["paint_source"] = str(args.paint)
    result["vehicle_archive"] = str(args.vehicle)
    result["cache_root"] = str(cache)
    result["helper_revision"] = WHEEL_MORPH_HELPER_REVISION
    result["helper_sha256"] = WHEEL_MORPH_HELPER_SHA256
    result["game_data_modified"] = False

    _write_result(result, output)
    return 0


def main() -> int:
    return run_manufacturer_materialbin_diagnostic()


if __name__ == "__main__":
    raise SystemExit(main())
