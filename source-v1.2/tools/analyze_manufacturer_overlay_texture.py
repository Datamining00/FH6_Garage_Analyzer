from __future__ import annotations

import argparse
import json
from pathlib import Path

from fh6garage.preview3d.livery_paint_provenance import LiveryPaintProvenanceError
from fh6garage.preview3d.manufacturer_colors import ManufacturerColorsError
from fh6garage.preview3d.manufacturer_overlay_texture_diagnostics import (
    diagnose_manufacturer_overlay_texture_payloads,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve direct .swatchbin payloads for exact FH6 manufacturer-overlay P3D candidates. "
            "This is diagnostic/cache-only: no DDS decode, UV4 sampling, rendering, or game-data modification."
        )
    )
    parser.add_argument("glb", help="Converted KFPS GLB")
    parser.add_argument("paint_source", help="C_livery file or containing Livery_* folder")
    parser.add_argument("vehicle_archive", help="Matching FH6 vehicle ZIP")
    parser.add_argument("cache_root", help="Diagnostic cache directory")
    parser.add_argument("output", help="Output JSON path")
    args = parser.parse_args()

    glb = Path(args.glb).resolve()
    paint_source = Path(args.paint_source).resolve()
    vehicle_archive = Path(args.vehicle_archive).resolve()
    cache_root = Path(args.cache_root).resolve()
    output = Path(args.output).resolve()

    protected = {glb, vehicle_archive}
    if paint_source.is_file():
        protected.add(paint_source)
    elif paint_source.is_dir():
        protected.add((paint_source / "C_livery").resolve())
    if output in protected:
        parser.error("Diagnostic output must not overwrite the GLB, C_livery, or vehicle archive.")

    try:
        report = diagnose_manufacturer_overlay_texture_payloads(
            glb, paint_source, vehicle_archive, cache_root
        )
    except (LiveryPaintProvenanceError, ManufacturerColorsError, OSError, ValueError) as exc:
        parser.error(str(exc))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
