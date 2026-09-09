from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from fh6garage.preview3d import material_runtime_wiring_patch as wiring


class _Scene:
    pass


class MaterialRuntimeWiringPatchTests(unittest.TestCase):
    def test_scene_source_path_registry_uses_object_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            scene = _Scene()
            glb = Path(temp) / "car.glb"
            wiring.remember_scene_glb_path(scene, glb)
            self.assertEqual(wiring.scene_glb_path(scene), str(glb.resolve()))
            other = _Scene()
            self.assertIsNone(wiring.scene_glb_path(other))

    def test_configure_populates_direct_widget_native_streams(self):
        scene = SimpleNamespace(positions=np.zeros((3, 3), dtype=np.float32))
        widget = SimpleNamespace(scene_data=scene)
        params = np.full((3, 4), 1.0, dtype=np.float32)
        aux = np.full((3, 4), 2.0, dtype=np.float32)
        f0 = np.full((3, 4), 3.0, dtype=np.float32)
        coat = np.full((3, 4), 4.0, dtype=np.float32)
        emission = np.full((3, 4), 5.0, dtype=np.float32)
        with patch(
            "fh6garage.preview3d.material_appearance_patch._build_material_vertex_streams_all",
            return_value=(params, aux, f0, coat, emission, 2, 1),
        ):
            self.assertTrue(wiring.configure_game_like_material_widget(widget, "car.glb"))
        self.assertIs(widget._fh6_material_params, params)
        self.assertIs(widget._fh6_material_aux, aux)
        self.assertIs(widget._fh6_material_f0, f0)
        self.assertIs(widget._fh6_material_coat_f0, coat)
        self.assertIs(widget._fh6_material_emission, emission)
        self.assertEqual(widget._fh6_native_material_primitives, 2)
        self.assertEqual(widget._fh6_native_optical_primitives, 1)
        self.assertEqual(widget._fh6_material_direct_wiring_status if hasattr(widget, "_fh6_material_direct_wiring_status") else "", "")

    def test_configure_fails_closed_to_existing_role_defaults(self):
        widget = SimpleNamespace(scene_data=SimpleNamespace())
        with patch(
            "fh6garage.preview3d.material_appearance_patch._build_material_vertex_streams_all",
            side_effect=ValueError("broken provenance"),
        ):
            self.assertFalse(wiring.configure_game_like_material_widget(widget, "car.glb"))
        self.assertIsNone(widget._fh6_material_params)
        self.assertIsNone(widget._fh6_material_aux)
        self.assertIn("broken provenance", widget._fh6_material_stream_error)
        self.assertEqual(widget._fh6_native_material_primitives, 0)
        self.assertEqual(widget._fh6_native_optical_primitives, 0)

    def test_lazy_installer_source_orders_material_patch_before_direct_wiring(self):
        root = Path(__file__).resolve().parents[1]
        init_text = (root / "fh6garage" / "preview3d" / "__init__.py").read_text(encoding="utf-8")
        material_pos = init_text.index("install_game_like_material_patch()")
        wiring_pos = init_text.index("install_material_runtime_wiring_patch()")
        texture_pos = init_text.index("install_native_material_texture_patch()")
        transform_pos = init_text.index("install_native_transform_chain_v3()")
        self.assertLess(material_pos, wiring_pos)
        self.assertLess(wiring_pos, texture_pos)
        self.assertLess(texture_pos, transform_pos)
        integration_text = (root / "fh6garage" / "preview3d" / "integration.py").read_text(encoding="utf-8")
        self.assertIn("viewer = CarOpenGLWidget(scene, self.textures, parent=self.dialog)", integration_text)

    def test_finalverify_installs_patches_before_importing_preview_controller(self):
        root = Path(__file__).resolve().parents[1]
        preview_text = (root / "fh6garage" / "v1_4_finalverify1_preview_patch.py").read_text(
            encoding="utf-8"
        )
        installer_call = preview_text.index("install_validated_fxx_native_tire_preview()")
        controller_import = preview_text.index("from .preview3d.integration import Preview3DController")
        self.assertLess(installer_call, controller_import)


if __name__ == "__main__":
    unittest.main()
