from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class V13RestartEnvironmentTests(unittest.TestCase):
    def test_onefile_restart_resets_pyinstaller_environment(self) -> None:
        source = (ROOT / 'fh6garage' / 'v1_3_ui_patch.py').read_text(encoding='utf-8')
        self.assertIn('PYINSTALLER_RESET_ENVIRONMENT', source)
        self.assertIn('os.environ[reset_key] = "1"', source)
        self.assertIn('program = sys.executable', source)
        self.assertLess(source.index('os.environ[reset_key] = "1"'), source.index('QProcess.startDetached(program, arguments)'))

    def test_restart_restores_parent_environment_after_spawn(self) -> None:
        source = (ROOT / 'fh6garage' / 'v1_3_ui_patch.py').read_text(encoding='utf-8')
        self.assertIn('previous_reset = os.environ.get(reset_key)', source)
        self.assertIn('os.environ.pop(reset_key, None)', source)
        self.assertIn('os.environ[reset_key] = previous_reset', source)

if __name__ == '__main__':
    unittest.main()
