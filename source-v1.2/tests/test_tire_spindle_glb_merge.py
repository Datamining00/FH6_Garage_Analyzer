from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from fh6garage.preview3d.tire_spindle_glb_merge import (
    TireSpindleGlbMergeError,
    merge_tire_spindle_trial_glb,
)


def _pad4(raw: bytes, padding: bytes = b"\x00") -> bytes:
    return raw + padding * ((-len(raw)) % 4)


def _write_glb(path: Path, document: dict, binary: bytes = b"") -> None:
    doc = json.loads(json.dumps(document))
    doc.setdefault("asset", {"version": "2.0"})
    doc["buffers"] = [{"byteLength": len(binary)}]
    json_raw = _pad4(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    bin_raw = _pad4(binary)
    total = 12 + 8 + len(json_raw) + 8 + len(bin_raw)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(json_raw), b"JSON")
        + json_raw
        + struct.pack("<I4s", len(bin_raw), b"BIN\x00")
        + bin_raw
    )


def _read_document(path: Path) -> dict:
    raw = path.read_bytes()
    length, chunk_type = struct.unpack_from("<II", raw, 12)
    if chunk_type != 0x4E4F534A:
        raise AssertionError("first GLB chunk is not JSON")
    return json.loads(raw[20:20 + length].rstrip(b" \x00").decode("utf-8"))


def _vehicle_glb(path: Path) -> None:
    document = {
        "asset": {"version": "2.0", "generator": "test vehicle"},
        "bufferViews": [],
        "accessors": [],
        "meshes": [],
        "nodes": [{"name": "existing body"}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    _write_glb(path, document)


def _tire_glb(path: Path, *, material: bool = False, transformed_node: bool = False) -> None:
    positions = struct.pack(
        "<fffffffff",
        0.0, 0.0, 0.0,
        0.1, 0.0, 0.0,
        0.0, 0.1, 0.0,
    )
    positions = _pad4(positions)
    index_offset = len(positions)
    indices = struct.pack("<III", 0, 1, 2)
    binary = _pad4(positions + indices)
    primitive = {"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}
    document = {
        "asset": {"version": "2.0", "generator": "test tire"},
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(indices), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [0.1, 0.1, 0.0],
            },
            {"bufferView": 1, "componentType": 5125, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [primitive]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    if material:
        document["materials"] = [{"name": "not allowed in first merge"}]
        primitive["material"] = 0
    if transformed_node:
        document["nodes"][0]["translation"] = [1.0, 0.0, 0.0]
    _write_glb(path, document, binary)


def _matrix(x: float, y: float, z: float, *, mirrored: bool = False) -> list[float]:
    return [
        -1.0 if mirrored else 1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, -1.0 if mirrored else 1.0, 0.0,
        x, y, z, 1.0,
    ]


def _contract(root: Path) -> dict:
    specs = [
        ("spindleLF", "front", "left", "tirel_slick.modelbin", "front_left.glb", _matrix(-0.976929, 0.204021, 1.321729)),
        ("spindleRF", "front", "right", "tireR_slick.modelbin", "front_right.glb", _matrix(0.976900, 0.204021, 1.321749, mirrored=True)),
        ("spindleLR", "rear", "left", "tirel_slick.modelbin", "rear_left.glb", _matrix(-0.996928, 0.204021, -1.323761)),
        ("spindleRR", "rear", "right", "tireR_slick.modelbin", "rear_right.glb", _matrix(0.996900, 0.204021, -1.323761, mirrored=True)),
    ]
    return {
        "format": "fh6_native_tire_spindle_attachment_contract_v2",
        "status": "spindle_attachment_contract_ready",
        "revision": "native_carbin_wheelstyle_spindle_contract_v2",
        "car_id": 1006,
        "attachment_part_type": 44,
        "tire_part_type": 44,
        "attachments": [
            {
                "spindle_bone": bone,
                "axle": axle,
                "side": side,
                "carbin_resource_path": f"game:/media/cars/fer_fxx_05/{bone}.modelbin",
                "carbin_transform_matrix_row_major": matrix,
                "derived_tire_entry": entry,
                "derived_tire_glb_path": str(root / filename),
            }
            for bone, axle, side, entry, filename, matrix in specs
        ],
        "native_carbin_transform_only": True,
        "procedural_translation_applied": False,
        "procedural_rotation_applied": False,
        "procedural_scale_applied": False,
        "spindle_attachment_contract_ready": True,
        "spindle_attachment_applied": False,
        "production_renderer_enabled": False,
    }


class TireSpindleGlbMergeTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, dict]:
        vehicle = root / "vehicle.glb"
        _vehicle_glb(vehicle)
        for name in ("front_left.glb", "front_right.glb", "rear_left.glb", "rear_right.glb"):
            _tire_glb(root / name)
        return vehicle, _contract(root)

    def test_successful_merge_preserves_source_and_native_matrices(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            source_before = hashlib.sha256(vehicle.read_bytes()).hexdigest()
            output = root / "vehicle_with_tires.glb"

            report = merge_tire_spindle_trial_glb(vehicle, contract, output)

            self.assertEqual(report.status, "spindle_tire_trial_glb_ready")
            self.assertEqual(report.car_id, 1006)
            self.assertTrue(report.source_vehicle_glb_unchanged)
            self.assertTrue(report.spindle_attachment_applied)
            self.assertTrue(report.trial_vehicle_glb_ready)
            self.assertFalse(report.production_renderer_enabled)
            self.assertEqual(hashlib.sha256(vehicle.read_bytes()).hexdigest(), source_before)
            self.assertTrue(output.is_file())
            self.assertEqual(len(report.merged_tire_nodes), 4)

            doc = _read_document(output)
            self.assertEqual(len(doc["nodes"]), 5)
            self.assertEqual(len(doc["meshes"]), 4)
            self.assertEqual(doc["scenes"][0]["nodes"], [0, 1, 2, 3, 4])
            for offset, attachment in enumerate(contract["attachments"], start=1):
                node = doc["nodes"][offset]
                self.assertEqual(node["matrix"], attachment["carbin_transform_matrix_row_major"])
                self.assertEqual(node["extras"]["spindle_bone"], attachment["spindle_bone"])
                self.assertTrue(node["extras"]["fh6_native_tire_trial"])

    def test_source_output_overlap_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            with self.assertRaisesRegex(TireSpindleGlbMergeError, "must not overwrite"):
                merge_tire_spindle_trial_glb(vehicle, contract, vehicle)

    def test_v1_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            contract["format"] = "fh6_native_tire_spindle_attachment_contract_v1"
            with self.assertRaisesRegex(TireSpindleGlbMergeError, "unsupported spindle"):
                merge_tire_spindle_trial_glb(vehicle, contract, root / "out.glb")

    def test_non_wheelstyle_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            contract["attachment_part_type"] = 8
            with self.assertRaisesRegex(TireSpindleGlbMergeError, "WheelStyle"):
                merge_tire_spindle_trial_glb(vehicle, contract, root / "out.glb")

    def test_missing_derivative_fails_closed_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            Path(contract["attachments"][2]["derived_tire_glb_path"]).unlink()
            output = root / "out.glb"
            with self.assertRaisesRegex(TireSpindleGlbMergeError, "does not exist"):
                merge_tire_spindle_trial_glb(vehicle, contract, output)
            self.assertFalse(output.exists())

    def test_derivative_material_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            _tire_glb(root / "front_left.glb", material=True)
            with self.assertRaisesRegex(TireSpindleGlbMergeError, "materials"):
                merge_tire_spindle_trial_glb(vehicle, contract, root / "out.glb")

    def test_derivative_node_transform_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            _tire_glb(root / "front_left.glb", transformed_node=True)
            with self.assertRaisesRegex(TireSpindleGlbMergeError, "unexpected transform"):
                merge_tire_spindle_trial_glb(vehicle, contract, root / "out.glb")

    def test_non_affine_matrix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vehicle, contract = self._fixture(root)
            contract["attachments"][0]["carbin_transform_matrix_row_major"][3] = 1.0
            with self.assertRaisesRegex(TireSpindleGlbMergeError, "not an affine"):
                merge_tire_spindle_trial_glb(vehicle, contract, root / "out.glb")


if __name__ == "__main__":
    unittest.main()
