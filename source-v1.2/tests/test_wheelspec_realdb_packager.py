from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "tools" / "package_wheelspec_realdb_diagnostic.py"


class WheelSpecRealDBPackagerTests(unittest.TestCase):
    def test_packager_contains_launcher_validator_and_minimal_package(self):
        text = PACKAGER.read_text(encoding="utf-8")
        self.assertIn("Run_FH6_WheelSpec_RealDB_Diagnostic.cmd", text)
        self.assertIn("validate_wheel_spec_real_db.py", text)
        self.assertIn("README_WheelSpec_RealDB_Diagnostic.txt", text)
        self.assertIn('ROOT / "fh6garage" / "preview3d" / "wheel_spec.py"', text)
        self.assertIn('make_archive', text)


if __name__ == "__main__":
    unittest.main()
