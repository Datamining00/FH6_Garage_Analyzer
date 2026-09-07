from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from fh6garage.preview3d.tire_morph_signature_comparison import (
    TireMorphSignatureComparisonError,
    compare_native_tire_selector_signatures,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnostic-only cross-family comparison of native FH6 tire selector geometry. "
            "Boundary motion is normalized by each modelbin baseline span."
        )
    )
    parser.add_argument(
        "archives",
        nargs="+",
        help="Two or more native tire_*.zip archives; the first is the reference.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.25,
        help="Diagnostic maximum normalized boundary-feature delta (default: 0.25).",
    )
    parser.add_argument(
        "--min-unique-families",
        type=int,
        default=2,
        help="Minimum distinct modelbin-geometry families required (default: 2).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Writable JSON report path outside the FH6 installation.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    archives = tuple(Path(value).expanduser().resolve() for value in args.archives)
    output = Path(args.output).expanduser().resolve()
    try:
        report = compare_native_tire_selector_signatures(
            archives,
            quantitative_tolerance=args.tolerance,
            minimum_unique_geometry_families=args.min_unique_families,
        )
    except TireMorphSignatureComparisonError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = report.as_dict()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
