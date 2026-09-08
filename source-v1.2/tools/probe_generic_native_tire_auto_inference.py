from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from fh6garage.preview3d.tire_asset import resolve_tire_archive
from fh6garage.preview3d.tire_morph_auto_inference import (
    TireMorphAutoInferenceError,
    infer_stock_native_tire_morph,
)
from fh6garage.preview3d.wheel_spec import FH6WheelSpecResolver
from fh6garage.preview3d.wheel_spec_database import ensure_stock_wheel_database


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read the installed FH6 stock wheel database and native tire modelbin, "
            "run generic tire morph auto-inference read-only, and write a JSON report."
        )
    )
    parser.add_argument(
        "--cars",
        required=True,
        help="FH6 Content/media/cars directory, or a path resolvable to it",
    )
    parser.add_argument("--car-id", required=True, type=int, help="Positive FH6 Car ID")
    parser.add_argument(
        "--output",
        help=(
            "Optional JSON output path. The inference also writes its persistent diagnostic "
            "below LocalAppData/FH6GarageAnalyzer/preview3d_runtime/diagnostics."
        ),
    )
    return parser


def _write_optional(path_text: str | None, payload: dict) -> str | None:
    if not path_text:
        return None
    path = Path(path_text).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.car_id <= 0:
        print("ERROR: --car-id must be positive", file=sys.stderr)
        return 2

    try:
        print("Resolving verified stock-wheel database...", flush=True)
        database = ensure_stock_wheel_database(lambda message: print(message, flush=True))
        spec = FH6WheelSpecResolver(database).resolve(args.car_id)
        tire_model = str(spec.tire_model_name or "").strip()
        if not tire_model:
            raise RuntimeError("stock wheel database returned no TireModelName")
        archive = resolve_tire_archive(args.cars, tire_model)
        print(f"Car ID: {spec.car_id}")
        print(f"TireModelName: {tire_model}")
        print(f"Native archive: {archive}")
        report = infer_stock_native_tire_morph(spec, archive)
        payload = {
            "format": "fh6_generic_native_tire_auto_inference_probe_v1",
            "status": "success",
            "wheel_spec": spec.as_dict(),
            "inference": report.as_dict(),
        }
        optional = _write_optional(args.output, payload)
        print("Generic native tire auto-inference: ACCEPTED")
        print(f"Persistent report: {report.persistent_report_path}")
        if optional:
            print(f"Requested report: {optional}")
        print(
            f"Front selectors={report.front.selector_weights} scale_x={report.front.scale_x:.9g} "
            f"radial_error={report.front.maximum_radial_relative_error:.3%}"
        )
        print(
            f"Rear selectors={report.rear.selector_weights} scale_x={report.rear.scale_x:.9g} "
            f"radial_error={report.rear.maximum_radial_relative_error:.3%}"
        )
        return 0
    except TireMorphAutoInferenceError as exc:
        payload = {
            "format": "fh6_generic_native_tire_auto_inference_probe_v1",
            "status": "rejected",
            "error": str(exc),
            "inference": exc.report,
            "persistent_report_path": exc.report_path,
        }
        optional = _write_optional(args.output, payload)
        print(f"Generic native tire auto-inference: REJECTED: {exc}", file=sys.stderr)
        if exc.report_path:
            print(f"Persistent report: {exc.report_path}", file=sys.stderr)
        if optional:
            print(f"Requested report: {optional}", file=sys.stderr)
        return 3
    except Exception as exc:
        payload = {
            "format": "fh6_generic_native_tire_auto_inference_probe_v1",
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
        optional = _write_optional(args.output, payload)
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        if optional:
            print(f"Requested report: {optional}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
