from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from fh6garage.preview3d.tire_morph_geometry import (
    TireMorphGeometryError,
    bake_tire_morph_selectors,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnostic-only native FH6 tire selector geometry bake. "
            "Writes baseline + selector0..4 GLBs and an AABB report without modifying the source ZIP."
        )
    )
    parser.add_argument("archive", help="Path to native tire_*.zip, e.g. tire_slick.zip")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Default: <archive stem>_selector_bake next to the archive.",
    )
    parser.add_argument(
        "--no-glb",
        action="store_true",
        help="Generate JSON/AABB evidence only.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    archive = Path(args.archive).expanduser().resolve()
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else archive.with_name(f"{archive.stem}_selector_bake")
    )
    try:
        report = bake_tire_morph_selectors(
            archive,
            output_dir,
            write_glb=not args.no_glb,
        )
    except TireMorphGeometryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "tire_selector_geometry_report.json"
    report_path.write_text(
        json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
