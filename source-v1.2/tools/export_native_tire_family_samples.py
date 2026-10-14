from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from fh6garage.preview3d.tire_family_export import (
    TireFamilyExportError,
    export_native_tire_family_samples,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only FH6 native tire family sample exporter. "
            "Copies unique non-Slick tire geometry families to a separate diagnostic bundle."
        )
    )
    parser.add_argument("game", help="FH6 game root or Content/media/cars path")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="New diagnostic output directory outside the FH6 installation tire library.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional TireModelName to exclude; may be repeated. Slick is excluded by default.",
    )
    parser.add_argument(
        "--include-slick",
        action="store_true",
        help="Include Slick instead of excluding it by default.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of unique modelbin-geometry families to copy (default: 5).",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    excluded = list(args.exclude)
    if not args.include_slick:
        excluded.append("Slick")
    try:
        report = export_native_tire_family_samples(
            Path(args.game),
            Path(args.output_dir),
            exclude_model_names=excluded,
            limit=args.limit,
        )
    except TireFamilyExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = report.as_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Bundle ready for upload: {report.bundle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
