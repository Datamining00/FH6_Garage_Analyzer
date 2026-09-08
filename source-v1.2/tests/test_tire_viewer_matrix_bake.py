from __future__ import annotations

import hashlib
from pathlib import Path
import struct
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


def _first_triangle(path: Path, node: dict) -> tuple[int, int, int]:
    document = _read_document(path)
    raw = path.read_bytes()
    json_length = struct.unpack_from("<I", raw, 12)[0]
    bin_header = 20 + json_length
    _bin_length, bin_type = struct.unpack_from("<II", raw, bin_header)
    if bin_type != 0x004E4942:
        raise AssertionError("fixture has no BIN chunk")
    binary_start = bin_header + 8

    mesh = document["meshes"][int(node["mesh"])]
    primitive = mesh["primitives"][0]
    accessor = document["accessors"][int(primitive["indices"])]
    view = document["bufferViews"][int(accessor["bufferView"])]
    formats = {5121: ("<B", 1), 5123: ("<H", 2), 5125: ("<I", 4)}
    fmt, size = formats[int(accessor["componentType"])]
    stride = int(view.get("byteStride", size))
    start = (
        binary_start
        + int(view.get("byteOffset", 0))
        + int(accessor.get("byteOffset", 0))
    )
    return tuple(
        int(struct.unpack_from(fmt, raw, start + index * stride)[0])
        for index in range(3)
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

    def test_bake_matches_kfps_render_coordinates_and_removes_root_matrices(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = self._merged_fixture(root)
            sha_before = hashlib.sha256(output.read_bytes()).hexdigest()

            before_document = _read_document(output)
            before_tire_nodes = [
                node
                for node in before_document["nodes"]
                if (node.get("extras") or {}).get("fh6_native_tire_trial") is True
            ]
            self.assertEqual(len(before_tire_nodes), 4)
            self.assertTrue(all(_first_triangle(output, node) == (0, 1, 2) for node in before_tire_nodes))

            report = bake_native_tire_trial_node_matrices(output)

            self.assertEqual(report["status"], "native_tire_trial_node_matrices_baked")
            self.assertEqual(report["format"], "fh6_native_tire_viewer_matrix_bake_v2")
            self.assertEqual(report["node_count"], 4)
            self.assertEqual(report["vertex_count"], 12)
            self.assertEqual(report["triangle_winding_reversed_count"], 4)
            self.assertFalse(report["native_matrix_only"])
            self.assertTrue(report["native_matrix_and_kfps_render_space_only"])
            self.assertTrue(report["kfps_render_space_reflection_applied"])
            self.assertEqual(report["kfps_render_space_rule"], "(-x,y,z)")
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
                self.assertTrue(node["extras"]["fh6_kfps_render_space_reflection_applied"])
                self.assertEqual(node["extras"]["fh6_kfps_render_space_rule"], "(-x,y,z)")
                self.assertEqual(_first_triangle(output, node), (0, 2, 1))

            # KFPS ChassisConverter emits (-X, Y, Z) after applying the native
            # carbin/bone transform. FinalVerify1 consumes the resulting POSITION
            # arrays directly, so the derived tire must use the identical render
            # coordinate convention. This specifically prevents LF/RF and LR/RR
            # tires from occupying the opposite lateral side from their rims.
            scene = load_kfps_glb(output, livery=None)
            self.assertEqual(scene.mesh_count, 4)
            self.assertEqual(scene.triangle_count, 4)
            self.assertEqual(len(scene.indices), 12)
            self.assertEqual(scene.role_counts.get("trim"), 4)
            self.assertEqual(len(scene.positions), 12)
            groups = scene.positions.reshape(4, 3, 3)
            expected_origins = np.asarray(
                [
                    [0.976929, 0.204021, 1.321729],
                    [-0.976900, 0.204021, 1.321749],
                    [0.996928, 0.204021, -1.323761],
                    [-0.996900, 0.204021, -1.323761],
                ],
                dtype=np.float32,
            )
            np.testing.assert_allclose(groups[:, 0, :], expected_origins, atol=2.0e-6)
            self.assertGreater(float(groups[0, 1, 0]), 0.87)
            self.assertLess(float(groups[1, 1, 0]), -0.87)
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
