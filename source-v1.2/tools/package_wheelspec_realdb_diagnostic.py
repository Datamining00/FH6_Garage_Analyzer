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
    ROOT / "fh6garage" / "preview3d" / "wheel_spec.py",
)
DIAGNOSTIC_PREVIEW3D_INIT = (
    '"""Minimal preview3d package for the standalone wheel-spec diagnostic."""\n'
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

    # Do not copy production preview3d/__init__.py into this deliberately minimal
    # diagnostic. Production package initialization installs geometry/tire hooks
    # whose modules are outside this small wheel-spec bundle.
    (preview3d_dir / "__init__.py").write_text(
        DIAGNOSTIC_PREVIEW3D_INIT,
        encoding="utf-8",
    )

    archive = shutil.make_archive(str(OUT), "zip", root_dir=OUT.parent, base_dir=OUT.name)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
