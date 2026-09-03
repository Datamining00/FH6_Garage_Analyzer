from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path("fh6garage/preview3d")


class Preview3DBackendStage2AContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_verified_backend_tree_is_present(self):
        required = {
            "vehicle_assets.py",
            "converter.py",
            "converter_base.py",
            "near_lod.py",
            "carbin.py",
            "modelbin.py",
            "neutral_geometry.py",
            "wheel_visibility.py",
            "kfps_runtime.py",
            "direct_livery.py",
            "glb_parser.py",
            "viewer.py",
            "integration.py",
            "THIRD_PARTY_NOTICES.md",
            "licenses/KFPS_LICENSE.txt",
            "licenses/FORZATECHSTUDIO_LICENSE.txt",
        }
        present = {
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in ROOT.rglob("*")
            if path.is_file()
        }
        self.assertTrue(required.issubset(present))

    def test_unverified_wheel_and_gamedb_work_is_not_ported(self):
        names = {path.name.casefold() for path in ROOT.rglob("*.py")}
        for rejected in (
            "wheel_assembly.py",
            "wheel_mesh_diagnostic.py",
            "tire_source_diagnostic.py",
            "gamedb_diagnostic.py",
            "gamedb_format_diagnostic.py",
        ):
            self.assertNotIn(rejected, names)

    def test_errorfix1_keeps_valid_glb_when_wheel_mapping_validation_fails(self):
        converter = self.read("converter.py")
        self.assertIn("from .converter_base import convert_vehicle as _convert_vehicle_base", converter)
        self.assertIn("from .wheel_visibility import", converter)
        self.assertIn("# ErrorFix1:", converter)
        self.assertIn('"validation_failed_proceeding"', converter)
        start = converter.index("if wheel_visibility_error:")
        end = converter.index('diagnostics["wheel_visibility_revision"]', start)
        fail_open_block = converter[start:end]
        self.assertNotIn("unlink", fail_open_block)
        self.assertNotIn("raise ChassisConverterError", fail_open_block)

    def test_errorfix1_is_applied_after_base_cache_or_conversion(self):
        converter = self.read("converter.py")
        base_call = converter.index("result = _convert_vehicle_base(")
        wheel_call = converter.index("apply_neutral_wheel_visibility(")
        self.assertLess(base_call, wheel_call)
        self.assertIn('diagnostics["glb_size"] = int(output.stat().st_size)', converter)

    def test_wheel_visibility_uses_structural_ordered_mapping_only(self):
        wheel = self.read("wheel_visibility.py")
        self.assertIn("from .modelbin import MeshStructureRecord, parse_modelbin_mesh_structures", wheel)
        self.assertIn("Validate every source/instance mapping before mutating", wheel)
        self.assertIn("WheelStyle ordered mapping failed index-count validation", wheel)
        self.assertIn("if result.motion_primitives_hidden > 0:", wheel)
        for rejected in ("FER_FXX", "TOY_2000GT", "MIN_JCWGP"):
            self.assertNotIn(rejected, wheel)

    def test_stage1_shell_is_preserved_below_the_stage2b_lazy_wrapper(self):
        base = Path("fh6garage/v1_4_preview_mode_shell_base.py").read_text(encoding="utf-8")
        wrapper = Path("fh6garage/v1_4_preview_mode_shell_patch.py").read_text(encoding="utf-8")
        self.assertNotIn("from .preview3d", base)
        self.assertIn("3D backend 연결 전 UI 검증 단계입니다.", base)
        self.assertIn("from .preview3d.integration import _prepare_preview_3d", wrapper)
        self.assertIn("QTimer.singleShot(0, invoke_backend)", wrapper)

    def test_localappdata_and_readonly_cache_contract_is_preserved(self):
        base = self.read("converter_base.py")
        wrapper = self.read("converter.py")
        self.assertIn('os.environ.get("LOCALAPPDATA")', base)
        self.assertIn('"FH6 Assistant" / "3d_preview"', base)
        self.assertIn('"neutral_geometry_revision": int(NEUTRAL_GEOMETRY_REVISION)', base)
        self.assertIn('diagnostics["game_data_modified"] = False', wrapper)

    def test_finalverify1_neutral_geometry_and_viewer_contracts_are_preserved(self):
        neutral = self.read("neutral_geometry.py")
        self.assertIn("'vehicle_specific_rules': False", neutral)
        self.assertIn("WHEEL_STYLE_PART_TYPE = 44", neutral)
        viewer = self.read("viewer.py")
        self.assertIn("vec3 L=normalize(vec3(0.45,0.85,0.55))", viewer)
        self.assertIn("0.34+0.66*d", viewer)
        self.assertIn("float rim=pow", viewer)
        self.assertIn("GL.glClearColor(0.5294118, 0.8078431, 0.9215686, 1.0)", viewer)

    def test_raster_and_uv3_fail_open_contracts_are_preserved(self):
        runtime = self.read("kfps_runtime.py")
        self.assertIn("_DECAL_MEMBER_RE", runtime)
        self.assertIn("self._members_by_id", runtime)
        self.assertIn("skipping ID(s) and continuing", runtime)
        self.assertNotIn("10009", runtime)
        self.assertNotIn("10010", runtime)
        parser = self.read("glb_parser.py")
        self.assertIn("if int(livery_uv_channel)!=3", parser)
        self.assertIn("{'strict','legacy'}", parser)
        self.assertIn("TEXCOORD_", parser)


if __name__ == "__main__":
    unittest.main()
