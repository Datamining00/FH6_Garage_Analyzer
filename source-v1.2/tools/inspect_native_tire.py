from __future__ import annotations

import argparse
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fh6garage.preview3d.tire_asset import (
    TireAssetError,
    compare_tire_library_to_database,
    inspect_tire_archive,
    report_json,
    scan_tire_library,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only FH6 native tire archive/library diagnostic."
    )
    parser.add_argument("game", help="FH6 install root or Content/media/cars directory")
    parser.add_argument(
        "tire_model_name",
        nargs="?",
        help="Exact DB TireModelName, for example Slick. Omit with --catalog/--db.",
    )
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="List all tire_*.zip assets without collapsing suffix variants.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="Read-only FH6 SQLite DB; compare every TireModelName with the native tire catalog.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path. Without this option JSON is printed to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.db is not None:
            report = compare_tire_library_to_database(args.game, args.db)
        elif args.catalog:
            report = scan_tire_library(args.game)
        else:
            if not args.tire_model_name:
                raise TireAssetError("tire_model_name is required unless --catalog or --db is used")
            report = inspect_tire_archive(args.game, args.tire_model_name)
        text = report_json(report)
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text + "\n", encoding="utf-8")
            print(output)
        else:
            print(text)
        return 0
    except (TireAssetError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
