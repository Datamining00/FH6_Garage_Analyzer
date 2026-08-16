from __future__ import annotations

from pathlib import Path

ROOT = Path('source-v1.2')


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8-sig')
    if old not in text:
        raise SystemExit(f'Expected fragment not found in {path}: {old!r}')
    path.write_text(text.replace(old, new), encoding='utf-8')


replace(ROOT / 'app.py', 'app.setApplicationVersion("1.1")', 'app.setApplicationVersion("1.2")')
replace(ROOT / 'fh6garage' / '__init__.py', '__version__ = "1.1"', '__version__ = "1.2"')
replace(ROOT / 'fh6garage' / 'ui.py', 'self.setWindowTitle("FH6 Assistant v1.1")', 'self.setWindowTitle("FH6 Assistant v1.2")')
replace(ROOT / 'fh6garage' / 'ui.py', 'version = QLabel("v1.1\\nLIVERY & TUNING")', 'version = QLabel("v1.2\\nLIVERY & TUNING")')
replace(ROOT / 'README.txt', 'FH6 Assistant v1.1', 'FH6 Assistant v1.2')
replace(ROOT / 'build_exe.ps1', '.\\FH6_Assistant_v1.1.spec', '.\\FH6_Assistant_v1.2.spec')
replace(ROOT / 'build_exe.ps1', 'dist\\FH6 Assistant v1.1.exe', 'dist\\FH6 Assistant v1.2.exe')

version_path = ROOT / 'version_info.txt'
version = version_path.read_text(encoding='utf-8-sig')
for old, new in (
    ('filevers=(1, 1, 0, 0)', 'filevers=(1, 2, 0, 0)'),
    ('prodvers=(1, 1, 0, 0)', 'prodvers=(1, 2, 0, 0)'),
    ("StringStruct('FileVersion', '1.1.0.0')", "StringStruct('FileVersion', '1.2.0.0')"),
    ("StringStruct('OriginalFilename', 'FH6 Assistant v1.1.exe')", "StringStruct('OriginalFilename', 'FH6 Assistant v1.2.exe')"),
    ("StringStruct('ProductVersion', '1.1')", "StringStruct('ProductVersion', '1.2')"),
):
    if old not in version:
        raise SystemExit(f'Expected version_info fragment not found: {old!r}')
    version = version.replace(old, new)
version_path.write_text(version, encoding='utf-8')

old_spec = ROOT / 'FH6_Assistant_v1.1.spec'
new_spec = ROOT / 'FH6_Assistant_v1.2.spec'
spec = old_spec.read_text(encoding='utf-8-sig')
if "name='FH6 Assistant v1.1'" not in spec:
    raise SystemExit('Expected v1.1 EXE name not found in spec')
spec = spec.replace("name='FH6 Assistant v1.1'", "name='FH6 Assistant v1.2'")
new_spec.write_text(spec, encoding='utf-8')
old_spec.unlink()

print('Applied FH6 Assistant v1.2 version metadata patch.')
