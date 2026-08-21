from __future__ import annotations

import argparse
from pathlib import Path

from .decoder import decode_clivery_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only FH6 C_livery Milestone 1 decoder"
    )
    parser.add_argument("source", type=Path, help="C_livery file or inflated vlrc payload")
    parser.add_argument("-o", "--output", type=Path, help="write JSON to this file instead of stdout")
    args = parser.parse_args()

    text = decode_clivery_file(args.source).to_json() + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
