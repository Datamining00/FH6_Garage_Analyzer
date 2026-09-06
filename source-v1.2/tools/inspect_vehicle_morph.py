from __future__ import annotations

import argparse
from pathlib import Path
import sys

from fh6garage.preview3d.vehicle_index import (
    VehicleIndexError,
    load_vehicle_asset,
    preferred_carbin_entry,
)
from fh6garage.preview3d.vehicle_morph_diagnostic import (
    VehicleMorphDiagnosticError,
    inspect_vehicle_morph_archive,
    report_json,
    write_vehicle_morph_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only FH6 vehicle modelbin morph inventory diagnostic."
    )
    parser.add_argument("archive", help="Vehicle ZIP archive")
    parser.add_argument("--carbin", help="Explicit carbin entry inside the ZIP")
    parser.add_argument("--model-code", help="Vehicle model code; defaults to archive stem")
    parser.add_argument(
        "--output",
        help="Optional JSON output path outside the source archive directory. Without this option JSON is printed to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    archive = Path(args.archive).expanduser().resolve()
    try:
        asset = load_vehicle_asset(archive)
        carbin = args.carbin or preferred_carbin_entry(asset)
        if carbin is None:
            choices = ", ".join(asset.carbin_entries) or "<none>"
            raise VehicleMorphDiagnosticError(
                "Vehicle archive does not have one unambiguous carbin entry. "
                f"Specify --carbin. Available entries: {choices}"
            )
        model_code = args.model_code or asset.model_code
        report = inspect_vehicle_morph_archive(archive, carbin, model_code)
        if args.output:
            output = write_vehicle_morph_report(report, args.output)
            print(output)
        else:
            print(report_json(report))
        return 0
    except (VehicleIndexError, VehicleMorphDiagnosticError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
