from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
LAUNCHER = ROOT / "tools" / "Run_FH6_P3F_Materialbin_Diagnostic.cmd"
SAFETY_PATCH = ROOT / "fh6garage" / "v1_3_2_safety_patch.py"


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

    def test_launcher_self_checks_packaged_helper_before_collecting_vehicle_input(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self_check = text.index("--p3f-materialbin-diagnostic --self-check")
        vehicle = text.index('set "VEHICLE=%~1"')
        self.assertLess(self_check, vehicle)
        self.assertIn("p3f_packaged_self_check.json", text)
        self.assertIn("packaged_p3f_self_check_passed", text)
        self.assertIn("packaged_contract_ready", text)

    def test_launcher_collects_vehicle_only_and_auto_prepares_glb_and_livery(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("--p3f-materialbin-diagnostic", text)
        self.assertIn("--vehicle", text)
        self.assertIn("--save-root", text)
        self.assertIn("--cache", text)
        self.assertIn("--output", text)
        self.assertNotIn("--glb", text)
        self.assertNotIn("--paint", text)
        self.assertNotIn(":pick_glb", text.casefold())
        self.assertNotIn(":pick_paint", text.casefold())
        self.assertIn("GLB     : AUTO", text)
        self.assertIn("C_livery: AUTO", text)
        self.assertIn(":pick_save_root", text)
        self.assertIn("No FH6 save path is available", text)
        self.assertIn("%LOCALAPPDATA%\\FH6 Assistant\\Diagnostics", text)
        self.assertIn("P3FCache", text)
        self.assertIn("GAME/SAVE READ-ONLY", text)
        self.assertIn("explorer.exe /select", text)
        self.assertNotIn("copy /y", text.casefold())
        self.assertNotIn("move /y", text.casefold())
        self.assertNotIn('del /q "%VEHICLE%"', text)

    def test_release_safety_patch_keeps_legacy_no_argument_startup_call_compatible(self):
        text = SAFETY_PATCH.read_text(encoding="utf-8")
        self.assertIn("def apply_v1_3_2_safety_patches(MainWindow=None)", text)
        self.assertIn("if MainWindow is None:", text)
        self.assertIn("from .ui import MainWindow as UiMainWindow", text)


if __name__ == "__main__":
    unittest.main()
