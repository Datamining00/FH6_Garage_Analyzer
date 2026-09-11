from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class VehicleMorphLauncherContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.launcher = cls.root / "tools" / "Run_FH6_Wheel_Morph_Diagnostic.cmd"
        cls.inspector = cls.root / "tools" / "inspect_vehicle_morph.py"
        cls.text = cls.launcher.read_text(encoding="utf-8")

    def test_launcher_uses_read_only_vehicle_morph_inspector(self):
        self.assertIn("inspect_vehicle_morph.py", self.text)
        self.assertIn("Mode   : READ-ONLY", self.text)
        self.assertIn("--output", self.text)

    def test_launcher_writes_outside_selected_archive_directory(self):
        self.assertIn("%LOCALAPPDATA%\\FH6 Assistant\\Diagnostics", self.text)
        self.assertIn('set "OUTPUT=%OUTDIR%\\%STEM%_morph_w3.json"', self.text)

    def test_launcher_supports_argument_or_zip_picker(self):
        self.assertIn('set "ARCHIVE=%~1"', self.text)
        self.assertIn("System.Windows.Forms.OpenFileDialog", self.text)
        self.assertIn("FH6 vehicle ZIP (*.zip)|*.zip", self.text)

    def test_launcher_does_not_install_or_modify_game_data(self):
        lowered = self.text.casefold()
        self.assertNotIn("pip install", lowered)
        self.assertNotIn("zipfile", lowered)
        self.assertNotIn("--normalize", lowered)

    def test_inspector_direct_script_resolves_sibling_fh6garage_package(self):
        completed = subprocess.run(
            [sys.executable, str(self.inspector), "--help"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Vehicle ZIP archive", completed.stdout)


if __name__ == "__main__":
    unittest.main()
