# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from fh6garage.build_metadata import PORTABLE_DIR_NAME, STANDARD_NAME

project_root = Path(SPECPATH)

a = Analysis(
    ['app.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / 'data' / 'car_names.json'), 'data'),
        (str(project_root / 'icons' / 'FH6_Assistant.ico'), 'icons'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=STANDARD_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / 'icons' / 'FH6_Assistant.ico'),
    version=str(project_root / 'version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=PORTABLE_DIR_NAME,
)
