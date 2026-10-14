from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fh6garage.preview3d.tire_asset import TireAssetError, tire_library_dir
from fh6garage.preview3d.tire_family_candidates import (
    TireFamilyCandidateError,
    select_stock_tire_family_candidates,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only FH6 diagnostic that selects representative stock Car IDs "
            "for distinct TireModelName families present in the native tire library."
        )
    )
    parser.add_argument("game", help="FH6 install root or Content/media/cars directory")
    parser.add_argument("--db", type=Path, required=True, help="FH6 SQLite database path")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="TireModelName to exclude. Repeat as needed, e.g. --exclude Slick.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Maximum unique families (default: 5)")
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
        tires = tire_library_dir(args.game).resolve()
        if _is_within(output, tires):
            raise TireAssetError(
                "--output must be outside the FH6 native tire library; the game installation is read-only"
            )
        report = select_stock_tire_family_candidates(
            args.game,
            args.db,
            exclude_model_names=args.exclude,
            limit=args.limit,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n"
        output.write_text(text, encoding="utf-8")
        print(text, end="")
        print(f"Report: {output}")
        return 0
    except (TireAssetError, TireFamilyCandidateError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
