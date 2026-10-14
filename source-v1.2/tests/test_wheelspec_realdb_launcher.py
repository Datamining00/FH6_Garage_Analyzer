from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "Run_FH6_WheelSpec_RealDB_Diagnostic.cmd"
VALIDATOR = ROOT / "tools" / "validate_wheel_spec_real_db.py"


class WheelSpecRealDBLauncherTests(unittest.TestCase):
    def test_launcher_exists_and_targets_read_only_validator(self):
        self.assertTrue(LAUNCHER.is_file())
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("validate_wheel_spec_real_db.py", text)
        self.assertIn("--car-id 1006", text)
        self.assertIn("FER_FXX_05_wheelspec_realdb.json", text)
        self.assertIn("READ-ONLY", text)

    def test_launcher_supports_argument_or_database_picker(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('set "DBFILE=%~1"', text)
        self.assertIn("System.Windows.Forms.OpenFileDialog", text)
        self.assertIn("SQLite database (*.sqlite;*.db)", text)

    def test_validator_still_opens_sqlite_read_only(self):
        text = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("?mode=ro", text)
        self.assertIn("PRAGMA query_only = ON", text)
        self.assertIn("sha256_before", text)
        self.assertIn("sha256_after", text)
        self.assertIn("read_only_unchanged", text)

    def test_validator_direct_script_resolves_sibling_fh6garage_package(self):
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("real read-only FH6 SQLite DB", completed.stdout)


if __name__ == "__main__":
    unittest.main()
