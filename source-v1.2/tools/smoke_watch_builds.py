"""Launch only the two task artifacts with automatic game scanning disabled."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

root = Path(sys.argv[1]).resolve()
results = []
for exe in (root / 'FH6 Assistant v1.5.exe',
            root / 'FH6 Assistant v1.5 Portable' / 'FH6 Assistant v1.5.exe'):
    with tempfile.TemporaryDirectory(prefix='fh6-smoke-') as state:
        settings = Path(state) / 'FH6GarageAnalyzer' / 'app_options.json'
        settings.parent.mkdir()
        settings.write_text(json.dumps({'auto_livery_detection': False, 'auto_backup': False}))
        env = dict(os.environ, LOCALAPPDATA=state, QT_QPA_PLATFORM='offscreen',
                   FH6_ASSISTANT_SMOKE_TEST_MS='1500')
        started = time.perf_counter()
        completed = subprocess.run([str(exe)], env=env, timeout=45,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        result = {'build': str(exe.relative_to(root)), 'exit_code': completed.returncode,
                  'elapsed_seconds': time.perf_counter() - started}
        print(json.dumps(result), flush=True)
        results.append(result)
        if completed.returncode:
            raise SystemExit(completed.returncode)
(root / 'validation' / 'packaged-smoke.json').write_text(json.dumps(results, indent=2))
