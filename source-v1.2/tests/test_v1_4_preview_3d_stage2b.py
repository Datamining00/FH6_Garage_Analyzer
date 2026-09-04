from __future__ import annotations

import unittest
from pathlib import Path


WRAPPER = Path("fh6garage/v1_4_preview_mode_shell_patch.py")
BASE = Path("fh6garage/v1_4_preview_mode_shell_base.py")
INTEGRATION = Path("fh6garage/preview3d/integration.py")
REQUIREMENTS = Path("requirements.txt")


class Preview3DStage2BContractTests(unittest.TestCase):
    def test_360_shell_is_preserved_and_public_patch_is_lazy(self):
        base = BASE.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("content_stack.setCurrentIndex(0)", base)
        self.assertIn("mode_buttons[0].setChecked(True)", base)
        self.assertNotIn("from .preview3d", base)
        self.assertIn('prepared = {"requested": False}', wrapper)
        self.assertIn('if prepared["requested"]:', wrapper)
        self.assertIn('prepared["requested"] = True', wrapper)
        self.assertIn("from .preview3d.integration import _prepare_preview_3d", wrapper)
        self.assertIn("QTimer.singleShot(0, invoke_backend)", wrapper)

    def test_finalverify1_errorfix1_default_is_uv3_strict(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        integration = INTEGRATION.read_text(encoding="utf-8")
        self.assertIn('eligibility.findData("strict")', wrapper)
        self.assertIn("eligibility.setCurrentIndex(strict_index)", wrapper)
        self.assertIn("livery_uv_channel=3", integration)
        self.assertIn('currentData() or "legacy"', integration)

    def test_runtime_dependencies_are_declared(self):
        requirements = REQUIREMENTS.read_text(encoding="utf-8").casefold()
        for dependency in ("pyside6", "pyopengl", "numpy", "pillow"):
            self.assertIn(dependency, requirements)

    def test_qthread_gui_controller_and_opengl_lifecycle_are_preserved(self):
        integration = INTEGRATION.read_text(encoding="utf-8")
        self.assertIn("class _InitialPreviewWorker(QObject)", integration)
        self.assertIn("class _SceneReloadWorker(QObject)", integration)
        self.assertIn("class _Preview3DController(QObject)", integration)
        self.assertIn("class _Preview3DJobLifecycle(QObject)", integration)
        self.assertIn("worker.moveToThread(thread)", integration)
        self.assertIn("thread.started.connect(worker.run)", integration)
        self.assertIn("worker.finished.connect(finished_slot)", integration)
        self.assertIn("worker.failed.connect(failed_slot)", integration)
        self.assertIn("thread.finished.connect(worker.deleteLater)", integration)
        self.assertIn("thread.finished.connect(thread.deleteLater)", integration)
        self.assertIn("@Slot(object)", integration)
        self.assertIn("dialog.destroyed.connect(self._dialog_destroyed)", integration)
        self.assertIn("fmt.setVersion(3, 3)", integration)
        self.assertIn("fmt.setProfile(QSurfaceFormat.CoreProfile)", integration)
        self.assertIn("viewer.setFormat(fmt)", integration)
        self.assertNotIn("QSurfaceFormat.setDefaultFormat", integration)

    def test_blank_viewer_repair_explicitly_exposes_and_repaints_gl_widget(self):
        integration = INTEGRATION.read_text(encoding="utf-8")
        self.assertIn("self.retired_viewers", integration)
        self.assertIn("def _retire_viewer", integration)
        self.assertIn("viewer.hide()", integration)
        self.assertIn("viewer.show()", integration)
        self.assertIn("viewer.raise_()", integration)
        self.assertIn("viewer.update()", integration)
        self.assertIn("QTimer.singleShot(0, viewer.update)", integration)
        self.assertNotIn("viewer.close()", integration)

    def test_errorfix1_wrapper_remains_converter_entrypoint(self):
        integration = INTEGRATION.read_text(encoding="utf-8")
        converter = Path("fh6garage/preview3d/converter.py").read_text(encoding="utf-8")
        self.assertIn("from .converter import convert_vehicle", integration)
        self.assertIn("# ErrorFix1:", converter)
        self.assertIn('"validation_failed_proceeding"', converter)

    def test_image_and_non_livery_paths_are_not_replaced(self):
        base = BASE.read_text(encoding="utf-8")
        self.assertIn("이미지 backend 연결 전 UI 검증 단계입니다.", base)
        self.assertIn("if not isinstance(record, LiveryRecord):", base)
        self.assertIn("original_show(window, record)", base)


if __name__ == "__main__":
    unittest.main()
