from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.material_inventory import (
    KFPS_CONVERTER_COMMIT,
    KFPS_SCENE_FORMAT,
    MATERIAL_INVENTORY_REVISION,
    build_material_inventory,
)


def _glb_bytes(document: dict) -> bytes:
    raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
    padded = raw + b" " * ((4 - len(raw) % 4) % 4)
    total = 12 + 8 + len(padded)
    return (
        b"glTF"
        + struct.pack("<II", 2, total)
        + struct.pack("<II", len(padded), 0x4E4F534A)
        + padded
    )


def _kfps_document(binding_hash: object = "0123456789ABCDEF") -> dict:
    extras = {
        "kfps_role": "paint",
        "kfps_source_entry": "scene/body.modelbin",
        "kfps_material_name": "carpaint.materialbin",
        "kfps_part_type": "CarBody",
        "kfps_instance_identity": "standard:carbody:0",
        "kfps_stock_part": True,
        "kfps_part_option_ids": [],
        "kfps_draw_groups": 1,
        "kfps_allowed_sides": 63,
        "kfps_projection_sides": 0,
        "kfps_material_binding_hash": binding_hash,
    }
    return {
        "asset": {"version": "2.0", "generator": "KFPS local chassis converter"},
        "scene": 0,
        "scenes": [{"nodes": [0], "extras": {"kfps_format": KFPS_SCENE_FORMAT}}],
        "nodes": [{"name": "body", "mesh": 0, "extras": dict(extras)}],
        "meshes": [
            {
                "name": "body",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "TEXCOORD_3": 3},
                        "indices": 4,
                        "mode": 4,
                    }
                ],
                "extras": dict(extras),
            }
        ],
        "accessors": [],
        "bufferViews": [],
        "buffers": [],
    }


class MaterialInventoryTests(unittest.TestCase):
    def _write(self, data: bytes) -> tuple[tempfile.TemporaryDirectory, Path]:
        owner = tempfile.TemporaryDirectory()
        path = Path(owner.name) / "car.glb"
        path.write_bytes(data)
        return owner, path

    def test_pinned_converter_contract_is_explicit(self):
        self.assertEqual(KFPS_CONVERTER_COMMIT, "6f53ca3c584d78659d06d4b4a39561db67d79345")
        self.assertEqual(KFPS_SCENE_FORMAT, "kfps_local_chassis_scene_v3")
        self.assertEqual(MATERIAL_INVENTORY_REVISION, 1)

    def test_reads_structural_kfps_material_binding_without_gltf_material_guessing(self):
        owner, path = self._write(_glb_bytes(_kfps_document()))
        with owner:
            before = path.read_bytes()
            report = build_material_inventory(path)
            after = path.read_bytes()

        self.assertEqual(before, after)
        self.assertFalse(report.game_data_modified)
        self.assertEqual(report.asset_generator, "KFPS local chassis converter")
        self.assertEqual(report.scene_format, KFPS_SCENE_FORMAT)
        self.assertEqual(report.gltf_material_count, 0)
        self.assertEqual(report.primitive_material_references, 0)
        self.assertEqual(report.resolved_binding_hashes, 1)
        self.assertEqual(report.extras_mismatch_meshes, 0)
        record = report.records[0]
        self.assertEqual(record.material_name, "carpaint.materialbin")
        self.assertEqual(record.material_binding_hash, "0123456789ABCDEF")
        self.assertEqual(record.material_binding_value, 0x0123456789ABCDEF)
        self.assertEqual(record.material_binding_status, "resolved")
        self.assertEqual(record.source_entry, "scene/body.modelbin")
        self.assertEqual(record.instance_identity, "standard:carbody:0")
        self.assertEqual(record.uv_channels, (0, 3))
        self.assertTrue(record.node_mesh_extras_match)

    def test_zero_binding_is_distinct_from_missing_and_is_not_inferred(self):
        owner, path = self._write(_glb_bytes(_kfps_document("0000000000000000")))
        with owner:
            report = build_material_inventory(path)
        self.assertEqual(report.zero_binding_hashes, 1)
        self.assertEqual(report.resolved_binding_hashes, 0)
        self.assertEqual(report.records[0].material_binding_status, "zero")
        self.assertEqual(report.records[0].material_binding_value, 0)

        document = _kfps_document()
        del document["meshes"][0]["extras"]["kfps_material_binding_hash"]
        del document["nodes"][0]["extras"]["kfps_material_binding_hash"]
        owner, path = self._write(_glb_bytes(document))
        with owner:
            report = build_material_inventory(path)
        self.assertEqual(report.missing_binding_hashes, 1)
        self.assertIsNone(report.records[0].material_binding_hash)
        self.assertIsNone(report.records[0].material_binding_value)
        self.assertEqual(report.records[0].material_binding_status, "missing")

    def test_malformed_binding_is_reported_not_reconstructed_from_material_name(self):
        owner, path = self._write(_glb_bytes(_kfps_document("not-a-hash")))
        with owner:
            report = build_material_inventory(path)
        self.assertEqual(report.malformed_binding_hashes, 1)
        record = report.records[0]
        self.assertEqual(record.material_name, "carpaint.materialbin")
        self.assertIsNone(record.material_binding_hash)
        self.assertIsNone(record.material_binding_value)
        self.assertEqual(record.material_binding_status, "malformed")

    def test_node_mesh_extras_mismatch_is_diagnostic_only(self):
        document = _kfps_document()
        document["nodes"][0]["extras"]["kfps_material_name"] = "different.materialbin"
        data = _glb_bytes(document)
        owner, path = self._write(data)
        with owner:
            report = build_material_inventory(path)
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(report.extras_mismatch_meshes, 1)
        self.assertFalse(report.records[0].node_mesh_extras_match)
        self.assertEqual(report.records[0].material_name, "carpaint.materialbin")

    def test_existing_gltf_material_reference_is_counted_but_not_used_as_kfps_binding(self):
        document = _kfps_document()
        document["materials"] = [{"name": "generic-gltf-material"}]
        document["meshes"][0]["primitives"][0]["material"] = 0
        owner, path = self._write(_glb_bytes(document))
        with owner:
            report = build_material_inventory(path)
        self.assertEqual(report.gltf_material_count, 1)
        self.assertEqual(report.primitive_material_references, 1)
        self.assertEqual(report.records[0].material_binding_hash, "0123456789ABCDEF")


if __name__ == "__main__":
    unittest.main()
