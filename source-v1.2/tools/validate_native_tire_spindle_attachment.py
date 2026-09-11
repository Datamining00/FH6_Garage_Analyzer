from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Permit direct `python tools/...py` execution from source-v1.2 without requiring
# callers to preconfigure PYTHONPATH.
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from fh6garage.preview3d.tire_spindle_attachment import (  # noqa: E402
    TireSpindleAttachmentError,
    build_tire_spindle_attachment_contract,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the first native tire spindle attachment contract from a read-only FH6 "
            "carbin and a production-trial tire geometry manifest. No vehicle GLB is modified."
        )
    )
    parser.add_argument("carbin", help="Extracted FH6 .carbin file")
    parser.add_argument(
        "trial_manifest",
        help="native_tire_production_trial_geometry.json from the gated tire geometry stage",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output spindle attachment contract JSON path",
    )
    args = parser.parse_args()

    carbin_path = Path(args.carbin).expanduser().resolve()
    manifest_path = Path(args.trial_manifest).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not carbin_path.is_file():
        parser.error(f"carbin does not exist: {carbin_path}")
    if not manifest_path.is_file():
        parser.error(f"trial manifest does not exist: {manifest_path}")

    try:
        trial = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(trial, dict):
            raise TireSpindleAttachmentError("trial manifest root must be a JSON object")
        contract = build_tire_spindle_attachment_contract(
            carbin_path.read_bytes(),
            trial,
            output_path=output_path,
        )
    except (OSError, json.JSONDecodeError, TireSpindleAttachmentError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(contract.as_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
