from __future__ import annotations

import argparse
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fh6garage.preview3d.tire_asset import (
    TireAssetError,
    inspect_tire_archive,
    report_json,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only FH6 native tire ZIP/modelbin locator."
    )
    parser.add_argument(
        "game_path",
        help="FH6 installation root, Content path, or Content/media/cars path",
    )
    parser.add_argument(
        "--tire-model",
        required=True,
        help="TireModelName from FH6 DB, for example Slick",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path. Output inside the FH6 media/cars tree is refused.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = inspect_tire_archive(args.game_path, args.tire_model)
        text = report_json(report)
        if args.output:
            output = Path(args.output).expanduser().resolve()
            cars_dir = Path(report.cars_dir).resolve()
            if output == cars_dir or output.is_relative_to(cars_dir):
                raise TireAssetError(
                    "refusing to write diagnostic output inside the FH6 media/cars tree"
                )
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
