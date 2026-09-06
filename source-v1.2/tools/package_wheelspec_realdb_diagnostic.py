from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "FH6-WheelSpec-RealDB-Diagnostic"
TOOLS = (
    ROOT / "tools" / "Run_FH6_WheelSpec_RealDB_Diagnostic.cmd",
    ROOT / "tools" / "README_WheelSpec_RealDB_Diagnostic.txt",
    ROOT / "tools" / "validate_wheel_spec_real_db.py",
)
PACKAGE_FILES = (
    ROOT / "fh6garage" / "__init__.py",
    ROOT / "fh6garage" / "preview3d" / "__init__.py",
    ROOT / "fh6garage" / "preview3d" / "wheel_spec.py",
)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)

    tools_dir = OUT / "tools"
    preview3d_dir = OUT / "fh6garage" / "preview3d"
    tools_dir.mkdir(parents=True, exist_ok=True)
    preview3d_dir.mkdir(parents=True, exist_ok=True)

    for source in TOOLS:
        shutil.copy2(source, tools_dir / source.name)

    for source in PACKAGE_FILES:
        relative = source.relative_to(ROOT)
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    archive = shutil.make_archive(str(OUT), "zip", root_dir=OUT.parent, base_dir=OUT.name)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
