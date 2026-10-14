from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fh6garage.preview3d.tire_asset import TireAssetError, tire_library_dir
from fh6garage.preview3d.tire_morph_cross_family_validation import (
    TireMorphCrossFamilyValidationError,
    validate_stock_tire_morph_families,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only FH6 stock native-tire cross-family diagnostic. "
            "Runs the complete stock formula/geometry validator for multiple car IDs "
            "and checks that distinct TireModelName families are independently corroborated."
        )
    )
    parser.add_argument("game", help="FH6 install root or Content/media/cars directory")
    parser.add_argument("--db", type=Path, required=True, help="FH6 SQLite database path")
    parser.add_argument(
        "--car-id",
        type=int,
        action="append",
        required=True,
        help="FH6 car ordinal/ID. Repeat for each stock vehicle to validate.",
    )
    parser.add_argument(
        "--min-unique-families",
        type=int,
        default=2,
        help="Minimum distinct TireModelName families required (default: 2).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="JSON output path outside the FH6 native tire library.",
    )
    return parser


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.expanduser().resolve()
    try:
        tires_dir = tire_library_dir(args.game).resolve()
        if _is_within(output, tires_dir):
            raise TireAssetError(
                "--output must be outside the FH6 native tire library; "
                "the game installation is read-only for this diagnostic"
            )
        report = validate_stock_tire_morph_families(
            args.game,
            args.db,
            args.car_id,
            min_unique_families=args.min_unique_families,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n"
        output.write_text(text, encoding="utf-8")
        print(text, end="")
        print(f"Report: {output}")
        return 0
    except (
        TireAssetError,
        TireMorphCrossFamilyValidationError,
        OSError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
