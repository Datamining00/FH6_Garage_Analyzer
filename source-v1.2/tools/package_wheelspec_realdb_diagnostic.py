from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "FH6-WheelSpec-RealDB-Diagnostic"
FILES = (
    ROOT / "tools" / "Run_FH6_WheelSpec_RealDB_Diagnostic.cmd",
    ROOT / "tools" / "README_WheelSpec_RealDB_Diagnostic.txt",
    ROOT / "tools" / "validate_wheel_spec_real_db.py",
)
PACKAGE_DIRS = (
    ROOT / "fh6garage",
)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "tools").mkdir(parents=True, exist_ok=True)

    for source in FILES:
        shutil.copy2(source, OUT / "tools" / source.name)
    for source in PACKAGE_DIRS:
        shutil.copytree(source, OUT / source.name)

    archive = shutil.make_archive(str(OUT), "zip", root_dir=OUT.parent, base_dir=OUT.name)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
