from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .manufacturer_materialbin_diagnostics import trace_manufacturer_materialbin_payloads
from .manufacturer_overlay_diagnostics import diagnose_manufacturer_overlay
from .wheel_morph_helper import WHEEL_MORPH_HELPER_REVISION, WHEEL_MORPH_HELPER_SHA256


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Paint P3F diagnostic: follow P3D-exact manufacturer .materialbin entries "
            "through exact MatL/Texture2D references to the first exact swatchbin."
        )
    )
    parser.add_argument("--glb", required=True, type=_existing_file)
    parser.add_argument("--paint", required=True, type=_existing_file, help="C_livery paint source")
    parser.add_argument("--vehicle", required=True, type=_existing_file, help="Selected FH6 vehicle ZIP")
    parser.add_argument("--cache", required=True, type=Path, help="Writable diagnostic cache root outside FH6 data")
    parser.add_argument("--output", type=Path, help="Optional diagnostic JSON output path")
    return parser


def run_manufacturer_materialbin_diagnostic(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    cache = args.cache.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output is not None else None

    protected_inputs = {args.glb, args.paint, args.vehicle}
    if output is not None and output in protected_inputs:
        raise SystemExit("Refusing to overwrite a diagnostic source input with JSON output.")
    if cache in protected_inputs:
        raise SystemExit("Refusing to use a diagnostic source file as the cache root.")

    p3d = diagnose_manufacturer_overlay(args.glb, args.paint, args.vehicle)
    traced = trace_manufacturer_materialbin_payloads(p3d, args.vehicle, cache)

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

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


def main() -> int:
    return run_manufacturer_materialbin_diagnostic()


if __name__ == "__main__":
    raise SystemExit(main())
