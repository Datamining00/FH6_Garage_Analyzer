from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from fh6garage.preview3d.glb_parser import load_kfps_glb
from fh6garage.preview3d.tire_spindle_glb_merge import merge_tire_spindle_trial_glb
from fh6garage.preview3d.tire_viewer_matrix_bake import (
    TireViewerMatrixBakeError,
    bake_native_tire_trial_node_matrices,
)
from tests.test_tire_spindle_glb_merge import (
    _contract,
    _read_document,
    _tire_glb,
    _vehicle_glb,
)


class TireViewerMatrixBakeTests(unittest.TestCase):
    def _merged_fixture(self, root: Path) -> Path:
        vehicle = root / "vehicle.glb"
        _vehicle_glb(vehicle)
        for name in (
            "front_left.glb",
            "front_right.glb",
            "rear_left.glb",
            "rear_right.glb",
        ):
            _tire_glb(root / name)
        output = root / "vehicle_with_native_tires.glb"
        merge_tire_spindle_trial_glb(vehicle, _contract(root), output)
        return output

    def test_bake_removes_root_matrices_and_places_geometry_in_world_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = self._merged_fixture(root)
            sha_before = hashlib.sha256(output.read_bytes()).hexdigest()

            report = bake_native_tire_trial_node_matrices(output)

            self.assertEqual(report["status"], "native_tire_trial_node_matrices_baked")
            self.assertEqual(report["node_count"], 4)
            self.assertEqual(report["vertex_count"], 12)
            self.assertTrue(report["native_matrix_only"])
            self.assertFalse(report["procedural_translation_applied"])
            self.assertFalse(report["procedural_rotation_applied"])
            self.assertFalse(report["procedural_scale_applied"])
            self.assertNotEqual(hashlib.sha256(output.read_bytes()).hexdigest(), sha_before)

            document = _read_document(output)
            tire_nodes = [
                node
                for node in document["nodes"]
                if (node.get("extras") or {}).get("fh6_native_tire_trial") is True
            ]
            self.assertEqual(len(tire_nodes), 4)
            for node in tire_nodes:
                self.assertNotIn("matrix", node)
                self.assertTrue(node["extras"]["fh6_viewer_matrix_baked"])

            # FinalVerify1 currently consumes POSITION arrays as baked world
            # coordinates.  This regression catches the exact screenshot failure:
            # without the bake all four derivative triangles overlap at the origin.
            scene = load_kfps_glb(output, livery=None)
            self.assertEqual(len(scene.positions), 12)
            groups = scene.positions.reshape(4, 3, 3)
            expected_origins = np.asarray(
                [
                    [-0.976929, 0.204021, 1.321729],
                    [0.976900, 0.204021, 1.321749],
                    [-0.996928, 0.204021, -1.323761],
                    [0.996900, 0.204021, -1.323761],
                ],
                dtype=np.float32,
            )
            np.testing.assert_allclose(groups[:, 0, :], expected_origins, atol=2.0e-6)
            self.assertLess(float(groups[0, 1, 0]), -0.87)
            self.assertGreater(float(groups[1, 1, 0]), 0.87)
            self.assertLess(float(groups[2, 0, 2]), -1.32)
            self.assertLess(float(groups[3, 0, 2]), -1.32)

    def test_bake_fails_closed_when_native_tire_node_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = self._merged_fixture(root)
            document = _read_document(output)
            document["nodes"][-1]["extras"]["fh6_native_tire_trial"] = False

            # Rewriting the synthetic fixture is unnecessary here: the helper is
            # required to fail unless the file itself contains exactly four marked
            # nodes, so use the test GLB writer from the merge fixture module.
            from tests.test_tire_spindle_glb_merge import _write_glb
            raw = output.read_bytes()
            # Preserve the existing BIN chunk while replacing only JSON.
            import struct
            json_length = struct.unpack_from("<I", raw, 12)[0]
            bin_header = 20 + json_length
            bin_length, bin_type = struct.unpack_from("<II", raw, bin_header)
            self.assertEqual(bin_type, 0x004E4942)
            binary = raw[bin_header + 8:bin_header + 8 + bin_length]
            _write_glb(output, document, binary)

            with self.assertRaisesRegex(TireViewerMatrixBakeError, "exactly four"):
                bake_native_tire_trial_node_matrices(output)


if __name__ == "__main__":
    unittest.main()
