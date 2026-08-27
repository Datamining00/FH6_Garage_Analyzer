# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH)

a = Analysis(
    ['app.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / 'data' / 'car_names.json'), 'data'),
        (str(project_root / 'icons' / 'FH6_Assistant.ico'), 'icons'),
        (str(project_root / 'icons' / 'paint_bucket.png'), 'icons'),
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
    name='FH6 Assistant v1.3.3 Beta',
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
    name='FH6 Assistant v1.3.3 Beta Portable',
)
