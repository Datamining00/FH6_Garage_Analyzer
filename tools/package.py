"""Create three local distributions; no publishing or source downloads."""
import json
from pathlib import Path
import shutil
import zipfile
from fetch_sources import ROOT, prepare, sha256

NOTICES = ('THIRD_PARTY_NOTICES.md', 'SOURCE_AND_RELINKING.md', 'DATA_PROVENANCE_REVIEW.md')
EXCLUDED = {'.git', '__pycache__', '.venv', '.build-venv', '.pytest_cache', 'build', 'dist'}

def source_files(archives):
    for name in ('README.md', 'DEVELOPING.md', 'KNOWN_ISSUES.md', 'CHANGELOG.md',
                 'verified-build-requirements.txt', '.gitignore', '.gitattributes', *NOTICES):
        yield ROOT / name
    for directory in ('source-v1.2', 'tools', 'docs', '.github'):
        for path in sorted((ROOT / directory).rglob('*')):
            relative = path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink() or any(x in EXCLUDED for x in relative.parts):
                continue
            if path.suffix in ('.pyc', '.pyo', '.log', '.download') or path.name.startswith('.env'):
                continue
            if 'third_party_sources' in relative.parts and path not in archives and path.suffix != '.json':
                continue
            if path.name == 'fh6_cars.json.gz':
                continue
            yield path

def write_zip(destination, files, base, prefix):
    pending = destination.with_suffix('.zip.pending')
    with zipfile.ZipFile(pending, 'w', allowZip64=True) as archive:
        for path in files:
            name = prefix + path.relative_to(base).as_posix()
            mode = zipfile.ZIP_STORED if path.suffix in ('.xz', '.gz', '.zip') else zipfile.ZIP_DEFLATED
            archive.write(path, name, compress_type=mode)
    with zipfile.ZipFile(pending) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP CRC failure: {bad}')
    pending.replace(destination)

def main():
    archives = prepare(verify_only=True)
    for name in NOTICES:
        if (ROOT / name).read_bytes() != (ROOT / 'source-v1.2' / name).read_bytes():
            raise ValueError(f'Root and app notice differ: {name}')
    standard = ROOT / 'dist/FH6 Assistant v1.5.exe'
    portable = ROOT / 'dist/FH6 Assistant v1.5 Portable'
    if not standard.is_file() or not (portable / standard.name).is_file():
        raise ValueError('Build both distributions before packaging.')
    portable_files = [p for p in sorted(portable.rglob('*')) if p.is_file()]
    if any('virtualkeyboard' in str(p).lower() for p in portable_files):
        raise ValueError('Unexpected Qt Virtual Keyboard in portable build')
    for name in NOTICES:
        if (portable / '_internal' / name).read_bytes() != (ROOT / name).read_bytes():
            raise ValueError(f'Rebuild required: bundled {name} is stale')
    # Compare embedded application code to the current source before packaging.
    import marshal
    from PyInstaller.archive.readers import CArchiveReader
    for executable in (standard, portable / standard.name):
        archive = CArchiveReader(str(executable))
        if any('virtualkeyboard' in name.lower() for name in archive.toc):
            raise ValueError('Unexpected Qt Virtual Keyboard in executable')
        pyz = archive.open_embedded_archive('PYZ.pyz')
        modules = [name for name in pyz.toc if name == 'fh6garage' or name.startswith('fh6garage.')]
        if not modules:
            raise ValueError('Application modules are missing')
        for module in modules:
            path = ROOT / 'source-v1.2' / Path(*module.split('.'))
            path = path / '__init__.py' if path.is_dir() else path.with_suffix('.py')
            code = pyz.extract(module)
            if code is None:
                raise ValueError(f'Missing module: {module}')
            expected = compile(path.read_bytes(), code.co_filename, 'exec', optimize=0)
            if code != expected:
                raise ValueError(f'Built source differs: {module}')
        entrypoint = marshal.loads(archive.extract('app'))
        expected = compile((ROOT / 'source-v1.2/app.py').read_bytes(),
                           entrypoint.co_filename, 'exec', optimize=0)
        if entrypoint != expected:
            raise ValueError('Built entry point differs from app.py')
    output = ROOT / 'artifacts/release'
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(standard, output / standard.name)
    portable_zip = output / 'FH6-Assistant-v1.5-Portable.zip'
    source_zip = output / 'FH6-Assistant-v1.5-Full-Source.zip'
    write_zip(portable_zip, portable_files, portable, portable.name + '/')
    write_zip(source_zip, source_files(archives), ROOT, 'FH6-Assistant-v1.5-Source/')
    files = [output / standard.name, portable_zip, source_zip]
    entries = [{'filename': p.name, 'size': p.stat().st_size, 'sha256': sha256(p)} for p in files]
    (output / 'SHA256SUMS.txt').write_text(''.join(f"{e['sha256']}  {e['filename']}\n" for e in entries), encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps({'version': '1.5',
        'release_status': 'pending_data_rights_confirmation', 'files': entries}, indent=2) + '\n', encoding='utf-8')
    for name in NOTICES:
        shutil.copy2(ROOT / name, output / name)
    print(f'Created three distributions: {output}')

if __name__ == '__main__':
    main()
