from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fh6garage.preview3d.wheel_spec import (  # noqa: E402
    FH6WheelSpecResolver,
    WheelUpgradeSelection,
    find_game_database,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve FH6 stock/effective wheel specifications from a read-only SQLite DB."
    )
    parser.add_argument("--car-id", type=int, required=True)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--front-rim-size-id", type=int)
    parser.add_argument("--rear-rim-size-id", type=int)
    parser.add_argument("--front-tire-width-id", type=int)
    parser.add_argument("--rear-tire-width-id", type=int)
    parser.add_argument("--front-aspect-ratio-id", type=int)
    parser.add_argument("--rear-aspect-ratio-id", type=int)
    parser.add_argument("--tire-compound-id", type=int)
    parser.add_argument("--wheel-style-id", type=int)
    parser.add_argument("--rear-wheel-style-id", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    database = find_game_database(args.db)
    selection = WheelUpgradeSelection(
        front_rim_size_id=args.front_rim_size_id,
        rear_rim_size_id=args.rear_rim_size_id,
        front_tire_width_id=args.front_tire_width_id,
        rear_tire_width_id=args.rear_tire_width_id,
        front_aspect_ratio_id=args.front_aspect_ratio_id,
        rear_aspect_ratio_id=args.rear_aspect_ratio_id,
        tire_compound_id=args.tire_compound_id,
        wheel_style_id=args.wheel_style_id,
        rear_wheel_style_id=args.rear_wheel_style_id,
    )
    spec = FH6WheelSpecResolver(database).resolve(args.car_id, selection)
    print(json.dumps(spec.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
