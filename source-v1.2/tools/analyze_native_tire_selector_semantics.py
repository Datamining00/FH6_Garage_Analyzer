from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from fh6garage.preview3d.tire_morph_semantic_evidence import (
    TireMorphSemanticEvidenceError,
    analyze_native_tire_selector_semantics,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnostic-only native FH6 tire selector semantic evidence. "
            "Combines observed boundary roles with pinned public reference input mappings."
        )
    )
    parser.add_argument("archive", help="Path to native tire_*.zip")
    parser.add_argument(
        "--output",
        required=True,
        help="Writable JSON report path outside the FH6 installation.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    archive = Path(args.archive).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    try:
        report = analyze_native_tire_selector_semantics(archive)
    except TireMorphSemanticEvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
