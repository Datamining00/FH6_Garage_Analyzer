from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "fh6garage" / "preview3d"


class FinalVerify1PreviewPortContractTests(unittest.TestCase):
    def test_port_is_layered_on_337_and_final_thread_fix_remains_last(self) -> None:
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn(
            "from fh6garage.v1_4_finalverify1_preview_patch import apply_v1_4_finalverify1_preview_patch",
            app,
        )
        release = app.index("def _apply_release_patch_stack")
        preview = app.index("apply_v1_4_finalverify1_preview_patch(MainWindow)", release)
        finalizer = app.index("def _apply_finalizer_patch_stack")
        affinity = app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)", finalizer)
        self.assertLess(preview, finalizer)
        self.assertLess(finalizer, affinity)

    def test_existing_livery_magnifier_is_the_only_integration_entry(self) -> None:
        patch = (ROOT / "fh6garage" / "v1_4_finalverify1_preview_patch.py").read_text(encoding="utf-8")
        integration = (PACKAGE / "integration.py").read_text(encoding="utf-8")
        self.assertIn("original_show_livery_image = MainWindow._show_livery_image", patch)
        self.assertIn("if not isinstance(record, LiveryRecord)", patch)
        self.assertIn('tabs.addTab(thumbnail_page, "썸네일")', patch)
        self.assertIn('tabs.addTab(three_d_page, "3D")', patch)
        self.assertIn('livery_path = getattr(self.record, "livery_path", None)', integration)
        self.assertNotIn("resolve_clivery", integration)
        self.assertNotIn("clivery_locator", integration)

    def test_requested_defaults_and_controls_are_exact(self) -> None:
        patch = (ROOT / "fh6garage" / "v1_4_finalverify1_preview_patch.py").read_text(encoding="utf-8")
        for key in ("normal", "high", "ultra4x", "extreme8x", "experimental16x"):
            self.assertIn(f'("{key}",', patch)
        self.assertIn('resolution.setCurrentIndex(resolution.findData("ultra4x"))', patch)
        self.assertIn('eligibility.setCurrentIndex(eligibility.findData("legacy"))', patch)
        self.assertIn("uv.setCurrentIndex(uv.findData(3))", patch)
        self.assertIn('cleanup_ab = QCheckBox("A+B 정리")', patch)
        self.assertIn("cleanup_ab.setChecked(True)", patch)
        self.assertIn('cleanup_c = QCheckBox("C 추가 정리")', patch)
        self.assertIn("cleanup_c.setChecked(False)", patch)

    def test_parser_supports_uv0_through_uv3_and_legacy_default(self) -> None:
        parser = (PACKAGE / "glb_parser.py").read_text(encoding="utf-8")
        self.assertIn('livery_eligibility: str = "legacy"', parser)
        self.assertIn("neutral_cleanup_ab: bool = True", parser)
        self.assertIn("neutral_cleanup_c: bool = False", parser)
        self.assertIn("livery_uv_channel not in (0, 1, 2, 3)", parser)
        self.assertIn("cleanup_ab and bool(extras.get(\"kfps_neutral_ab_hidden\"", parser)

    def test_finalverify1_geometry_and_raster_policies_are_present(self) -> None:
        neutral = (PACKAGE / "neutral_geometry.py").read_text(encoding="utf-8")
        renderer = (PACKAGE / "kfps_render_backend.py").read_text(encoding="utf-8")
        viewer = (PACKAGE / "glb_viewer.py").read_text(encoding="utf-8")
        self.assertIn("wheelstyle_hidden_no_tire_runtime", neutral)
        self.assertIn("extreme_thin_auxiliary_geometry", neutral)
        self.assertIn("kfps_neutral_c_candidate", neutral)
        self.assertIn("_prepare_raster_layers", renderer)
        self.assertIn("skipped_raster_ids", renderer)
        self.assertIn("GL.glClearColor(0.5294118, 0.8078431, 0.9215686, 1.0)", viewer)

    def test_no_persistent_analysis_or_render_cache_output_is_used(self) -> None:
        converter = (PACKAGE / "chassis_converter.py").read_text(encoding="utf-8")
        renderer = (PACKAGE / "kfps_render_backend.py").read_text(encoding="utf-8")
        viewer = (PACKAGE / "glb_viewer.py").read_text(encoding="utf-8")
        integration = (PACKAGE / "integration.py").read_text(encoding="utf-8")
        self.assertNotIn("write_wheel_mesh_diagnostic", converter)
        self.assertIn("apply_neutral_wheel_visibility", converter)
        self.assertIn('validation_failed_proceeding', converter)
        self.assertIn('if wheel_visibility_error:', converter)
        self.assertNotIn('sidecar = output.with_suffix(".json")', converter)
        self.assertNotIn(".livery-eligibility.json", viewer)
        self.assertIn("TemporaryDirectory", integration)
        self.assertIn("output_root=render_root", integration)
        self.assertIn('raise KfpsRenderError("A transient output_root is required', renderer)
        self.assertFalse((PACKAGE / "cache_policy.py").exists())
        self.assertFalse((PACKAGE / "scene_cache.py").exists())
        self.assertFalse((PACKAGE / "gamedb_diagnostic.py").exists())
        self.assertFalse((PACKAGE / "tire_source_diagnostic.py").exists())

    def test_runtime_dependencies_are_declared(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("PySide6>=6.7,<7", requirements)
        self.assertIn("PyOpenGL>=3.1.7,<4", requirements)
        self.assertIn("numpy>=2.0,<3", requirements)
        self.assertIn("Pillow>=10,<13", requirements)


if __name__ == "__main__":
    unittest.main()
