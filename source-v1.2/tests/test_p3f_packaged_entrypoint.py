from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
LAUNCHER = ROOT / "tools" / "Run_FH6_P3F_Materialbin_Diagnostic.cmd"


class P3fPackagedEntrypointTests(unittest.TestCase):
    def test_app_dispatches_p3f_before_qapplication_and_ui_patch_stack(self):
        text = APP.read_text(encoding="utf-8")
        flag = text.index('_P3F_DIAGNOSTIC_FLAG = "--p3f-materialbin-diagnostic"')
        main = text.index("def main() -> int:")
        dispatch = text.index("special_result = _run_special_cli_mode()", main)
        qapplication = text.index("app = QApplication(sys.argv)", dispatch)
        patches = text.index("_apply_runtime_patch_stack()", dispatch)
        self.assertLess(flag, main)
        self.assertLess(dispatch, qapplication)
        self.assertLess(dispatch, patches)
        self.assertIn("run_manufacturer_materialbin_diagnostic", text)

    def test_launcher_uses_packaged_exe_and_localappdata_diagnostic_outputs(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("--p3f-materialbin-diagnostic", text)
        self.assertIn("--glb", text)
        self.assertIn("--paint", text)
        self.assertIn("--vehicle", text)
        self.assertIn("--cache", text)
        self.assertIn("--output", text)
        self.assertIn("%LOCALAPPDATA%\\FH6 Assistant\\Diagnostics", text)
        self.assertIn("P3FCache", text)
        self.assertIn("GAME/SAVE READ-ONLY", text)
        self.assertIn("explorer.exe /select", text)
        self.assertNotIn("copy /y", text.casefold())
        self.assertNotIn("move /y", text.casefold())
        self.assertNotIn("del /q \"%PAINT%\"", text)
        self.assertNotIn("del /q \"%VEHICLE%\"", text)
        self.assertNotIn("del /q \"%GLB%\"", text)


if __name__ == "__main__":
    unittest.main()
