from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from fh6garage.preview3d.tire_cross_family_diagnostic import (
    TireCrossFamilyDiagnosticError,
    run_native_tire_cross_family_diagnostic,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "One-click read-only FH6 native tire diagnostic: copy Slick reference, "
            "export unique non-reference tire families, compare normalized selector signatures, "
            "and create one shareable bundle."
        )
    )
    parser.add_argument("game", help="FH6 game root or Content/media/cars path")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="New diagnostic output directory outside the native FH6 tire library.",
    )
    parser.add_argument(
        "--reference",
        default="Slick",
        help="Reference TireModelName (default: Slick).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional TireModelName to exclude from candidates; may be repeated.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=5,
        help="Maximum number of unique non-reference modelbin families to export (default: 5).",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.25,
        help="Diagnostic normalized signature tolerance (default: 0.25; not a production threshold).",
    )
    parser.add_argument(
        "--min-unique-families",
        type=int,
        default=2,
        help="Minimum unique geometry families including the reference (default: 2).",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = run_native_tire_cross_family_diagnostic(
            Path(args.game),
            Path(args.output_dir),
            reference_model_name=args.reference,
            exclude_model_names=args.exclude,
            candidate_limit=args.candidate_limit,
            quantitative_tolerance=args.tolerance,
            minimum_unique_geometry_families=args.min_unique_families,
        )
    except TireCrossFamilyDiagnosticError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    print(f"Comparison report: {report.comparison_report_path}")
    print(f"Bundle ready for upload: {report.bundle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
