from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path("fh6garage/preview3d")


class Preview3DBackendContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_minimal_backend_files_are_present(self):
        required = {
            "vehicle_assets.py",
            "converter.py",
            "near_lod.py",
            "carbin.py",
            "modelbin.py",
            "neutral_geometry.py",
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

    def test_abandoned_tire_gamedb_and_wheel_validator_are_not_migrated(self):
        names = {path.name.casefold() for path in ROOT.rglob("*.py")}
        self.assertNotIn("wheel_visibility.py", names)
        self.assertNotIn("wheel_assembly.py", names)
        self.assertNotIn("tire_source_diagnostic.py", names)
        self.assertNotIn("gamedb_diagnostic.py", names)
        self.assertNotIn("gamedb_format_diagnostic.py", names)
        converter = self.read("converter.py").casefold()
        self.assertNotIn("wheel_visibility", converter)
        self.assertNotIn("write_wheel_mesh_diagnostic", converter)
        self.assertNotIn("gamedb", converter)

    def test_derived_runtime_and_cache_are_localappdata_only(self):
        converter = self.read("converter.py")
        runtime = self.read("kfps_runtime.py")
        self.assertIn('os.environ.get("LOCALAPPDATA")', converter)
        self.assertIn('"FH6 Assistant" / "3d_preview"', converter)
        self.assertIn("'FH6 Assistant' / '3d_preview'", runtime)
        self.assertIn("game_data_modified", converter)
        self.assertIn("False", converter)

    def test_preview_mode_lazy_imports_3d_backend(self):
        preview = Path("fh6garage/v1_4_preview_mode_patch.py").read_text(encoding="utf-8")
        self.assertIn("from .preview3d.integration import _prepare_preview_3d", preview)
        self.assertIn('prepared = {"requested": False}', preview)
        self.assertIn("prepare_three_d()", preview)
        self.assertIn("content_stack.setCurrentIndex(1)", preview)

    def test_requirements_include_3d_dependencies(self):
        requirements = Path("requirements.txt").read_text(encoding="utf-8").casefold()
        for dependency in ("pyopengl", "numpy", "pillow"):
            self.assertIn(dependency, requirements)

    def test_finalverify1_lighting_and_sky_background_are_preserved(self):
        viewer = self.read("viewer.py")
        self.assertIn("vec3 L=normalize(vec3(0.45,0.85,0.55))", viewer)
        self.assertIn("0.34+0.66*d", viewer)
        self.assertIn("float rim=pow", viewer)
        self.assertIn(
            "GL.glClearColor(0.5294118, 0.8078431, 0.9215686, 1.0)",
            viewer,
        )
        for rejected in ("Omni studio", "uKeyLightDir", "uFillLightDir", "shadow map", "PCF"):
            self.assertNotIn(rejected, viewer)

    def test_glb_parser_uses_uv3_and_two_ui_eligibility_modes(self):
        parser = self.read("glb_parser.py")
        self.assertIn("livery_uv_channel", parser)
        self.assertIn("strict", parser)
        self.assertIn("legacy", parser)
        self.assertIn("TEXCOORD_", parser)
        self.assertIn("neutral_cleanup_c", parser)
        preview = Path("fh6garage/v1_4_preview_mode_patch.py").read_text(encoding="utf-8")
        self.assertIn('eligibility.addItem("Legacy", "legacy")', preview)
        self.assertIn('eligibility.addItem("Strict", "strict")', preview)
        self.assertNotIn("declared_confirmed", preview)

    def test_raster_resolution_is_inventory_based_and_fail_open_per_layer(self):
        runtime = self.read("kfps_runtime.py")
        self.assertIn("_DECAL_MEMBER_RE", runtime)
        self.assertIn("self._members_by_id", runtime)
        self.assertIn("skipping ID(s) and continuing", runtime)
        self.assertNotIn("10009", runtime)
        self.assertNotIn("10010", runtime)

    def test_neutral_geometry_has_no_vehicle_specific_rules(self):
        neutral = self.read("neutral_geometry.py")
        self.assertIn("'vehicle_specific_rules': False", neutral)
        self.assertIn("WHEEL_STYLE_PART_TYPE = 44", neutral)
        for vehicle_literal in ("FXX", "2000GT", "JCWGP", "Toyota", "Ferrari", "MINI"):
            self.assertNotIn(vehicle_literal, neutral)

    def test_worker_architecture_matches_finalverify1_qthread_pattern(self):
        integration = self.read("integration.py")
        self.assertIn("class _InitialPreviewThread(QThread)", integration)
        self.assertIn("class _SceneReloadThread(QThread)", integration)
        self.assertIn("class _Preview3DController(QObject)", integration)
        self.assertIn("worker.completed.connect(self.initial_completed)", integration)
        self.assertIn("worker.completed.connect(self.reload_completed)", integration)
        self.assertIn("worker.message.connect(self.on_message)", integration)
        self.assertIn("@Slot(object)", integration)
        self.assertIn("QApplication.instance()", integration)
        self.assertIn("QThread.currentThread() != app.thread()", integration)
        self.assertNotIn("QThread.currentThread() is not app.thread()", integration)
        self.assertNotIn("moveToThread", integration)
        self.assertNotIn("_GuiJobRelay", integration)

    def test_dialog_lifecycle_preserves_reusable_status_widget(self):
        integration = self.read("integration.py")
        self.assertIn("dialog.destroyed.connect(self._dialog_destroyed)", integration)
        self.assertIn("if child is self.message", integration)
        self.assertIn("self.message.hide()", integration)
        self.assertIn("self.layout.addWidget(self.message, 1)", integration)
        self.assertNotIn("self.message.deleteLater", integration)

    def test_visible_gl_widget_and_mode_switch_are_native_context_safe(self):
        integration = self.read("integration.py")
        self.assertIn("self.retired_viewers", integration)
        self.assertIn("def _retire_viewer", integration)
        self.assertIn("viewer.hide()", integration)
        self.assertIn("viewer.show()", integration)
        self.assertIn("viewer.raise_()", integration)
        self.assertIn("viewer.update()", integration)
        self.assertNotIn("viewer.close()", integration)
        self.assertIn('currentData() or "legacy"', integration)

    def test_opengl_format_is_requested_per_lazy_widget(self):
        integration = self.read("integration.py")
        self.assertIn("QSurfaceFormat", integration)
        self.assertIn("fmt.setVersion(3, 3)", integration)
        self.assertIn("fmt.setProfile(QSurfaceFormat.CoreProfile)", integration)
        self.assertIn("viewer.setFormat(fmt)", integration)
        self.assertNotIn("QSurfaceFormat.setDefaultFormat", integration)
        self.assertNotIn("configure_default_opengl_format", integration)

    def test_loading_stages_distinguish_scene_decode_from_view_install(self):
        integration = self.read("integration.py")
        self.assertIn("3D 텍스처 계약 준비 중", integration)
        self.assertIn("3D 장면 준비 중", integration)
        self.assertIn("3D 장면 해석 완료", integration)
        self.assertIn("time.perf_counter()", integration)

    def test_third_party_notices_pin_the_audited_revisions(self):
        notices = self.read("THIRD_PARTY_NOTICES.md")
        self.assertIn("6f53ca3c584d78659d06d4b4a39561db67d79345", notices)
        self.assertIn("4f373c5fb192551ce5249e320dd79b1399b693ca", notices)
        self.assertIn("MIT", self.read("licenses/KFPS_LICENSE.txt"))
        self.assertIn("MIT License", self.read("licenses/FORZATECHSTUDIO_LICENSE.txt"))


if __name__ == "__main__":
    unittest.main()
