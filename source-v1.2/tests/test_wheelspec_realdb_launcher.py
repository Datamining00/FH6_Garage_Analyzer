from __future__ import annotations

from pathlib import Path
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

    def test_validator_still_opens_sqlite_read_only(self):
        text = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("?mode=ro", text)
        self.assertIn("PRAGMA query_only = ON", text)
        self.assertIn("sha256_before", text)
        self.assertIn("sha256_after", text)
        self.assertIn("read_only_unchanged", text)


if __name__ == "__main__":
    unittest.main()
