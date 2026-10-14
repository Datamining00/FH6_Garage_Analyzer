from __future__ import annotations

import argparse
from pathlib import Path

from fh6garage.preview3d.livery_paint_provenance import (
    LiveryPaintProvenanceError,
    write_livery_paint_diagnostic,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read an FH6 C_livery paint descriptor and write a read-only Paint P1 provenance JSON. "
            "Manufacturer selectors and finish codes remain raw/uninterpreted."
        )
    )
    parser.add_argument("source", help="C_livery file or its containing Livery_* folder")
    parser.add_argument("output", help="Output JSON path; must not overwrite C_livery")
    args = parser.parse_args()
    try:
        output = write_livery_paint_diagnostic(Path(args.source), Path(args.output))
    except LiveryPaintProvenanceError as exc:
        parser.error(str(exc))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
