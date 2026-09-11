from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from fh6garage.preview3d.tire_spindle_glb_merge import (  # noqa: E402
    TireSpindleGlbMergeError,
    merge_tire_spindle_trial_glb,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge four gated native tire derivative GLBs into a separate vehicle GLB "
            "using the exact WheelStyle spindle matrices from a validated v2 contract."
        )
    )
    parser.add_argument("vehicle_glb", help="Existing derived FH6 vehicle GLB (read-only input).")
    parser.add_argument("attachment_contract", help="Validated fh6_native_tire_spindle_attachment_contract_v2 JSON.")
    parser.add_argument("--output", required=True, help="New trial vehicle GLB path. The input GLB is never overwritten.")
    parser.add_argument(
        "--report",
        default=None,
        help="Optional JSON report path. Defaults beside --output with .tire-spindle-merge.json suffix.",
    )
    args = parser.parse_args()

    vehicle = Path(args.vehicle_glb).expanduser().resolve()
    contract_path = Path(args.attachment_contract).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else output.with_suffix(".tire-spindle-merge.json")
    )

    if not contract_path.is_file():
        parser.error(f"attachment contract does not exist: {contract_path}")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.error(f"could not read attachment contract: {exc}")
    if not isinstance(contract, dict):
        parser.error("attachment contract JSON root must be an object")

    try:
        report = merge_tire_spindle_trial_glb(vehicle, contract, output)
    except TireSpindleGlbMergeError as exc:
        parser.error(str(exc))

    payload = report.as_dict()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
