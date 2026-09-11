from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fh6garage.preview3d.modelbin_morph import (  # noqa: E402
    ModelbinMorphError,
    parse_modelbin_morph_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Forza modelbin morph buffers and mesh bindings read-only."
    )
    parser.add_argument("modelbin", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    path = args.modelbin.expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"modelbin does not exist: {path}")

    original = path.read_bytes()
    try:
        inventory = parse_modelbin_morph_inventory(original)
    except ModelbinMorphError as exc:
        raise SystemExit(f"morph inspection failed: {exc}") from exc

    report = inventory.as_dict()
    report["source"] = {
        "name": path.name,
        "size": len(original),
        "read_only": True,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
