# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH)

datas = [
    (str(project_root / 'licenses'), 'licenses'),
    (str(project_root / 'THIRD_PARTY_NOTICES.md'), '.'),
    (str(project_root / 'SOURCE_AND_RELINKING.md'), '.'),
    (str(project_root / 'DATA_PROVENANCE_REVIEW.md'), '.'),
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
    'fh6garage.preview3d.manufacturer_materialbin_cli',
    'fh6garage.preview3d.native_transform_chain_patch',
    'fh6garage.preview3d.native_transform_chain_v2',
    'fh6garage.preview3d.native_transform_chain_v3',
    'fh6garage.preview3d.tire_preview_integration',
    'fh6garage.preview3d.tire_preview_cache_patch',
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
    excludes=['PySide6.QtVirtualKeyboard'],
    noarchive=False,
    optimize=0,
)
# QtGui collects input plugins even without a Python import. Exclude both
# the unused GPL virtual keyboard plugin and its native module explicitly.
a.binaries = [entry for entry in a.binaries
              if 'virtualkeyboard' not in entry[0].lower()]
a.datas = [entry for entry in a.datas
           if 'virtualkeyboard' not in entry[0].lower()]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FH6 Assistant v1.5',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / 'icons' / 'FH6_Assistant.ico'),
    version=str(project_root / 'version_info.txt'),
)