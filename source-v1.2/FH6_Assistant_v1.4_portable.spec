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

wheel_morph_helper = project_root / 'runtime' / 'Kfps.ChassisConverter.WheelMorph.exe'
if wheel_morph_helper.is_file():
    datas.append((str(wheel_morph_helper), 'runtime'))

native_tire_hiddenimports = [
    'fh6garage.preview3d.material_appearance_patch',
    'fh6garage.preview3d.material_runtime_wiring_patch',
    'fh6garage.preview3d.livery_paint_provenance',
    'fh6garage.preview3d.livery_paint_runtime_patch',
    'fh6garage.preview3d.livery_paint_binding',
    'fh6garage.preview3d.livery_paint_secondary_diagnostics',
    'fh6garage.preview3d.manufacturer_colors',
    'fh6garage.preview3d.manufacturer_overlay_diagnostics',
    'fh6garage.preview3d.manufacturer_overlay_texture_diagnostics',
    'fh6garage.preview3d.exact_game_asset',
    'fh6garage.preview3d.materialbin_reference_helper',
    'fh6garage.preview3d.manufacturer_materialbin_diagnostics',
    'fh6garage.preview3d.native_transform_chain_patch',
    'fh6garage.preview3d.native_transform_chain_v2',
    'fh6garage.preview3d.native_transform_chain_v3',
    'fh6garage.preview3d.tire_preview_integration',
    'fh6garage.preview3d.tire_asset',
    'fh6garage.preview3d.tire_production_policy',
    'fh6garage.preview3d.tire_production_trial_geometry',
    'fh6garage.preview3d.tire_spindle_attachment',
    'fh6garage.preview3d.tire_spindle_glb_merge',
    'fh6garage.preview3d.tire_viewer_matrix_bake',
]

a = Analysis(
    ['app.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=native_tire_hiddenimports,
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
    name='FH6 Assistant v1.4',
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
    name='FH6 Assistant v1.4 Portable',
)
