"""Verify frozen modules against sources and the selected historical build."""
import json
from pathlib import Path
from zipfile import ZipFile
from PyInstaller.archive.readers import CArchiveReader

source = Path(__file__).resolve().parents[1]
repo = source.parents[2]
out = repo / 'artifacts' / 'auto-detection-ui-update'
baseline = repo / 'artifacts' / 'auto-detection' / 'FH6 Assistant v1.4.exe'
results = {}
with ZipFile(repo / 'work' / 'auto-detection-ui-base.zip') as original:
    archive = CArchiveReader(str(baseline)).open_embedded_archive('PYZ.pyz')
    checks = {}
    for name in archive.toc:
        if not name.startswith('fh6garage.'):
            continue
        path = 'source-v1.2/' + name.replace('.', '/') + '.py'
        if path not in original.namelist():
            path = path[:-3] + '/__init__.py'
        if path not in original.namelist():
            continue
        packed = archive.extract(name)
        checks[name] = packed == compile(original.read(path), packed.co_filename, 'exec', dont_inherit=True)
    results['baseline_66d01d0'] = checks
for exe in (out / 'FH6 Assistant v1.4.exe', out / 'FH6 Assistant v1.4 Portable' / 'FH6 Assistant v1.4.exe'):
    archive = CArchiveReader(str(exe)).open_embedded_archive('PYZ.pyz')
    checks = {}
    for name in archive.toc:
        if not name.startswith('fh6garage.'):
            continue
        path = source / (name.replace('.', '/') + '.py')
        if not path.exists():
            path = path.with_suffix('') / '__init__.py'
        assert path.exists(), name
        packed = archive.extract(name)
        checks[name] = packed == compile(path.read_bytes(), packed.co_filename, 'exec', dont_inherit=True)
    for excluded in ('backup_user_records', 'render_cache_ui', 'deferred_livery_cards'):
        assert 'fh6garage.' + excluded not in archive.toc
    results[str(exe.relative_to(out))] = checks
(out / 'validation' / 'packaged-source-check.json').write_text(json.dumps(results, indent=2), encoding='utf8')
for name, checks in results.items():
    print(name, len(checks), 'modules; mismatches:', [key for key, value in checks.items() if not value])
assert all(all(checks.values()) for checks in results.values())
