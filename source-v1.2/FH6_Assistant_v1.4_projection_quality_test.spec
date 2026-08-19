# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH)
vendor_root = project_root / 'vendor' / 'kfps'

if not vendor_root.is_dir():
    raise SystemExit(
        'Pinned KFPS livery preview backend is missing. '
        'Run the v1.4 Projection Quality Test build workflow or populate source-v1.2/vendor/kfps first.'
    )

required_vendor_files = [
    vendor_root / 'json_preview_renderer.py',
    vendor_root / 'geometry_json.py',
    vendor_root / 'tools' / 'cgroup' / 'forza_source_decoder.py',
    vendor_root / 'tools' / 'cgroup' / 'shape_identity.py',
    vendor_root / 'tools' / 'livery' / '__init__.py',
    vendor_root / 'tools' / 'livery' / 'vehicle_assets.py',
    vendor_root / 'tools' / 'livery' / 'render_contract.py',
    vendor_root / 'tools' / 'livery' / 'raster_decals.py',
    vendor_root / 'tools' / 'fabric-editor' / 'shape-words.json',
    vendor_root / 'tools' / 'fabric-editor' / 'Resources' / 'Vinyls',
    vendor_root / 'LICENSE',
]
missing = [str(path) for path in required_vendor_files if not path.exists()]
if missing:
    raise SystemExit('Incomplete KFPS preview backend:\n' + '\n'.join(missing))

datas = [
    (str(project_root / 'data' / 'car_names.json'), 'data'),
    (str(project_root / 'icons' / 'FH6_Assistant.ico'), 'icons'),
    (str(vendor_root / 'tools' / 'fabric-editor' / 'shape-words.json'), 'tools/fabric-editor'),
    (str(vendor_root / 'tools' / 'fabric-editor' / 'Resources' / 'Vinyls'), 'tools/fabric-editor/Resources/Vinyls'),
    (str(vendor_root / 'LICENSE'), 'vendor/kfps'),
]
shape_names = vendor_root / 'tools' / 'fabric-editor' / 'shape-names.json'
if shape_names.is_file():
    datas.append((str(shape_names), 'tools/fabric-editor'))

a = Analysis(
    ['app.py'],
    pathex=[str(vendor_root), str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'geometry_json',
        'json_preview_renderer',
        'tools.cgroup.forza_source_decoder',
        'tools.cgroup.shape_identity',
        'tools.livery.vehicle_assets',
        'tools.livery.render_contract',
        'tools.livery.raster_decals',
        'psutil',
    ],
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
    name='FH6 Assistant v1.4 Projection Quality Test',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / 'icons' / 'FH6_Assistant.ico'),
    version=str(project_root / 'version_info_projection_quality_test.txt'),
)
