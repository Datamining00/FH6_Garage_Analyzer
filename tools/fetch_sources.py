"""Fetch fixed third-party sources; verify existing archives without downloading."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'source-v1.2/third_party_sources'

def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def manifests():
    qt = json.loads((DEST / 'manifest.json').read_text(encoding='utf-8-sig'))
    gl = json.loads((DEST / 'PyOpenGL-source.json').read_text(encoding='utf-8-sig'))
    return qt['sources'] + [gl]

def target(name):
    if Path(name).name != name or '\\' in name or '/' in name:
        raise ValueError(f'Invalid archive name: {name}')
    return DEST / name

def fetch_archive(item, verify_only):
    path = target(item['filename'])
    if path.is_file() and sha256(path) == item['sha256']:
        return path
    if verify_only:
        raise ValueError(f'Missing or invalid source archive: {path.name}')
    if not item['url'].startswith('https://'):
        raise ValueError('Source downloads require HTTPS')
    pending = path.with_name(path.name + '.download')
    with urllib.request.urlopen(item['url'], timeout=120) as response, pending.open('wb') as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
    if sha256(pending) != item['sha256']:
        raise ValueError(f'Checksum mismatch: {pending}')
    pending.replace(path)
    return path

def blob_hash(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()

def verify_kfps(path, info):
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            if sorted(archive.namelist()) != sorted(x['path'] for x in info['files']):
                return False
            return all(blob_hash(archive.read(x['path'])) == x['sha'] for x in info['files'])
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return False

def fetch_kfps(verify_only):
    info = json.loads((DEST / 'KFPS-converter-source.json').read_text(encoding='utf-8-sig'))
    path = target(info['filename'])
    if verify_kfps(path, info):
        return path
    if verify_only:
        raise ValueError(f'Missing or invalid source archive: {path.name}')
    pending = path.with_name(path.name + '.download')
    with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for item in info['files']:
            relative = PurePosixPath(item['path'])
            if relative.is_absolute() or '..' in relative.parts or '\\' in item['path']:
                raise ValueError('Unsafe source path')
            url = f"https://raw.githubusercontent.com/{info['repository']}/{info['commit']}/{item['path']}"
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            if blob_hash(data) != item['sha']:
                raise ValueError(f"Git blob mismatch: {item['path']}")
            entry = zipfile.ZipInfo(item['path'], date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    if not verify_kfps(pending, info):
        raise ValueError('Generated converter archive failed verification')
    pending.replace(path)
    return path

def prepare(verify_only=False):
    paths = []
    for item in manifests():
        paths.append(fetch_archive(item, verify_only))
        print(f'Verified {paths[-1].name}', flush=True)
    paths.append(fetch_kfps(verify_only))
    print(f'Verified {paths[-1].name}', flush=True)
    return paths

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    prepare(parser.parse_args().verify_only)
