from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fh6garage.preview3d.wheel_placement import FH6WheelPlacementResolver  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve W1.2 wheel placement/brake specs from a real read-only FH6 DB."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--car-id", type=int, action="append", dest="car_ids")
    args = parser.parse_args()

    database = args.db.resolve()
    resolver = FH6WheelPlacementResolver(database)
    car_ids = args.car_ids or [1006, 1229, 1260]
    resolved = {}
    failures = {}
    for car_id in car_ids:
        try:
            resolved[str(car_id)] = resolver.resolve(car_id).as_dict()
        except Exception as exc:
            failures[str(car_id)] = f"{type(exc).__name__}: {exc}"

    report = {
        "format": "fh6_wheel_placement_real_db_validation_v1",
        "database": database.name,
        "resolved": resolved,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if "1006" in failures:
        raise SystemExit("Car ID 1006 placement resolution failed: " + failures["1006"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
