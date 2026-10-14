"""Exercise the actual workflow's minimal bundles without the source tree on sys.path."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


class DiagnosticBundleImportsTest(unittest.TestCase):
    def test_workflow_bundles_have_transitive_imports(self):
        repo = Path(__file__).resolve().parents[2]
        workflow = (repo / 'docs/history/workflows/validate-v1.4-wheel-morph-w3.yml').read_text(encoding='utf-8')
        for job, module in (
            ('package-four-way-bake-diagnostic', 'wheel_visibility'),
            ('package-diagnostic', 'vehicle_morph_diagnostic'),
        ):
            with self.subTest(job=job), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                block = workflow.split('\n  ' + job + ':', 1)[1].split('\n  package-', 1)[0]
                sources = re.findall(r'Copy-Item "(source-v1\.2\\fh6garage\\[^"\n]+\.py)"', block)
                self.assertTrue(sources)
                for source in sources:
                    relative = Path(source.replace('\\', '/'))
                    target = root / relative.relative_to('source-v1.2')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(repo / relative, target)
                (root / 'fh6garage/preview3d/__init__.py').write_text('', encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, '-I', '-c',
                     f'import sys; sys.path.insert(0, {str(root)!r}); import fh6garage.preview3d.{module}'],
                    cwd=root, capture_output=True, text=True,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
