from __future__ import annotations

import argparse
import json
from pathlib import Path

from fh6garage.preview3d.livery_paint_provenance import LiveryPaintProvenanceError
from fh6garage.preview3d.manufacturer_colors import ManufacturerColorsError
from fh6garage.preview3d.manufacturer_overlay_diagnostics import diagnose_manufacturer_overlay


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose exact FH6 manufacturer swatch overlay candidates without rendering or modifying game data. "
            "Requires a converted KFPS GLB, C_livery source, and the matching vehicle ZIP."
        )
    )
    parser.add_argument("glb", help="Converted KFPS GLB with exact material binding/name and TEXCOORD_n provenance")
    parser.add_argument("paint_source", help="C_livery file or its containing Livery_* folder")
    parser.add_argument("vehicle_archive", help="Matching FH6 vehicle ZIP containing ManufacturerColors.bin")
    parser.add_argument("output", help="Output diagnostic JSON path")
    args = parser.parse_args()

    glb = Path(args.glb).resolve()
    paint_source = Path(args.paint_source).resolve()
    vehicle_archive = Path(args.vehicle_archive).resolve()
    output = Path(args.output).resolve()
    protected = {glb, vehicle_archive}
    if paint_source.is_file():
        protected.add(paint_source)
    elif paint_source.is_dir():
        protected.add((paint_source / "C_livery").resolve())
    if output in protected:
        parser.error("Diagnostic output must not overwrite the GLB, C_livery, or vehicle archive.")

    try:
        report = diagnose_manufacturer_overlay(glb, paint_source, vehicle_archive)
    except (LiveryPaintProvenanceError, ManufacturerColorsError, OSError, ValueError) as exc:
        parser.error(str(exc))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
