from __future__ import annotations

import argparse
import json
from pathlib import Path

from fh6garage.preview3d.manufacturer_materialbin_diagnostics import (
    trace_manufacturer_materialbin_payloads,
)
from fh6garage.preview3d.manufacturer_overlay_diagnostics import diagnose_manufacturer_overlay


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Paint P3F diagnostic: follow P3D-exact manufacturer .materialbin entries "
            "through exact MatL/Texture2D references to the first exact swatchbin."
        )
    )
    parser.add_argument("--glb", required=True, type=Path)
    parser.add_argument("--paint", required=True, type=Path, help="C_livery paint source")
    parser.add_argument("--vehicle", required=True, type=Path, help="Selected FH6 vehicle ZIP")
    parser.add_argument("--cache", required=True, type=Path, help="Read-only diagnostic cache root")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    p3d = diagnose_manufacturer_overlay(args.glb, args.paint, args.vehicle)
    result = trace_manufacturer_materialbin_payloads(
        p3d,
        args.vehicle,
        args.cache,
    )
    result = dict(result)
    result["p3d_status"] = p3d.get("status")
    result["p3d_exact_candidate_count"] = p3d.get("exact_candidate_count")
    result["glb_file"] = str(args.glb)
    result["paint_source"] = str(args.paint)
    result["vehicle_archive"] = str(args.vehicle)
    result["cache_root"] = str(args.cache)

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
