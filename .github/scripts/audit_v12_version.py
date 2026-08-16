from __future__ import annotations

from pathlib import Path

ROOT = Path('source-v1.2')
SUFFIXES = {'.py', '.ps1', '.bat', '.vbs', '.txt', '.spec', '.md', '.yml', '.yaml'}
TOKENS = ('v1.1', '1.1.0.0', '1, 1, 0, 0', '"1.1"', "'1.1'")

hits: list[tuple[str, int, str]] = []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or path.suffix.lower() not in SUFFIXES:
        continue
    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        if any(token in line for token in TOKENS):
            hits.append((path.as_posix(), lineno, line.strip()))

print(f'Old-version occurrences: {len(hits)}')
for path, lineno, line in hits:
    print(f'{path}:{lineno}: {line}')
