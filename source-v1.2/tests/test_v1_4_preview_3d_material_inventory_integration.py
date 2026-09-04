from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fh6garage.preview3d import converter
from fh6garage.preview3d.converter_base import ConversionResult
from fh6garage.preview3d.material_inventory import MaterialInventoryError


class MaterialInventoryIntegrationTests(unittest.TestCase):
    def _fixture(self):
        owner = tempfile.TemporaryDirectory()
        root = Path(owner.name)
        output = root / "car.glb"
        output.write_bytes(b"glTF-derived-valid-output")
        archive = root / "car.zip"
        archive.write_bytes(b"read-only-source")
        asset = SimpleNamespace(archive_path=str(archive))
        return owner, output, archive, asset

    @staticmethod
    def _wheel_ok():
        return SimpleNamespace(as_dict=lambda: {"status": "ok"})

    def test_successful_inventory_writes_compact_sidecar_summary(self):
        owner, output, archive, asset = self._fixture()
        report = SimpleNamespace(
            source_name="car.glb",
            asset_generator="KFPS local chassis converter",
            scene_format="kfps_local_chassis_scene_v3",
            mesh_count=472,
            node_count=472,
            gltf_material_count=0,
            primitive_material_references=0,
            resolved_binding_hashes=24,
            zero_binding_hashes=448,
            missing_binding_hashes=0,
            malformed_binding_hashes=0,
            extras_mismatch_meshes=0,
            game_data_modified=False,
        )
        with owner, \
             patch.object(converter, "_convert_vehicle_base", return_value=ConversionResult(str(output), {"base": True})), \
             patch.object(converter, "apply_neutral_wheel_visibility", return_value=self._wheel_ok()), \
             patch.object(converter, "build_material_inventory", return_value=report):
            result = converter.convert_vehicle(asset, carbin_entry="scene.carbin")
            sidecar = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))

        self.assertEqual(result.output_path, str(output))
        self.assertEqual(sidecar["material_inventory_status"], "ok")
        self.assertIsNone(sidecar["material_inventory_error"])
        self.assertEqual(sidecar["material_inventory"]["resolved_binding_hashes"], 24)
        self.assertEqual(sidecar["material_inventory"]["gltf_material_count"], 0)
        self.assertNotIn("records", sidecar["material_inventory"])
        self.assertFalse(sidecar["game_data_modified"])
        self.assertEqual(archive.read_bytes(), b"read-only-source")

    def test_inventory_failure_is_fail_open_and_keeps_valid_glb(self):
        owner, output, archive, asset = self._fixture()
        original_glb = output.read_bytes()
        with owner, \
             patch.object(converter, "_convert_vehicle_base", return_value=ConversionResult(str(output), {"base": True})), \
             patch.object(converter, "apply_neutral_wheel_visibility", return_value=self._wheel_ok()), \
             patch.object(converter, "build_material_inventory", side_effect=MaterialInventoryError("synthetic inventory failure")):
            result = converter.convert_vehicle(asset, carbin_entry="scene.carbin")
            sidecar = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            retained = output.read_bytes()

        self.assertEqual(result.output_path, str(output))
        self.assertEqual(retained, original_glb)
        self.assertEqual(sidecar["material_inventory_status"], "failed_proceeding")
        self.assertEqual(sidecar["material_inventory"], {})
        self.assertIn("MaterialInventoryError", sidecar["material_inventory_error"])
        self.assertFalse(sidecar["game_data_modified"])
        self.assertEqual(archive.read_bytes(), b"read-only-source")

    def test_inventory_runs_after_wheel_postprocessing(self):
        owner, output, archive, asset = self._fixture()
        order: list[str] = []

        def wheel(*_args, **_kwargs):
            order.append("wheel")
            return self._wheel_ok()

        def inventory(*_args, **_kwargs):
            order.append("inventory")
            raise MaterialInventoryError("stop after order check")

        with owner, \
             patch.object(converter, "_convert_vehicle_base", return_value=ConversionResult(str(output), {})), \
             patch.object(converter, "apply_neutral_wheel_visibility", side_effect=wheel), \
             patch.object(converter, "build_material_inventory", side_effect=inventory):
            converter.convert_vehicle(asset, carbin_entry="scene.carbin")

        self.assertEqual(order, ["wheel", "inventory"])


if __name__ == "__main__":
    unittest.main()
