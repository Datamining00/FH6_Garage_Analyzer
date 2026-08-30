# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH)

datas = [
    (str(project_root / 'data' / 'car_names.json'), 'data'),
    (str(project_root / 'icons' / 'FH6_Assistant.ico'), 'icons'),
    (str(project_root / 'icons' / 'cards'), 'icons/cards'),
]
vehicle_data = project_root / 'data' / 'fh6_assistant_vehicle_data'
if vehicle_data.is_dir():
    datas.append((str(vehicle_data), 'data/fh6_assistant_vehicle_data'))

a = Analysis(
    ['app.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
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
    a.binaries,
    a.datas,
    [],
    name='FH6 Assistant v1.4',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / 'icons' / 'FH6_Assistant.ico'),
    version=str(project_root / 'version_info.txt'),
)
