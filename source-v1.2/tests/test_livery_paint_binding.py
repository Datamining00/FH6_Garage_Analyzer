from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from fh6garage.preview3d.livery_paint_binding import apply_exact_livery_paint_to_aux_stream


BODY = 0xF7DBE8A7C839A675
HOOD = 0x6AC1E9D87FE5D953


def _write_glb(path: Path, mesh_specs: list[tuple[str | None, int]]) -> None:
    accessors = []
    meshes = []
    nodes = []
    for index, (binding, vertex_count) in enumerate(mesh_specs):
        accessor_index = len(accessors)
        accessors.append({"count": int(vertex_count)})
        extras = {"kfps_role": "paint"}
        if binding is not None:
            extras["kfps_material_binding_hash"] = binding
        meshes.append({"extras": extras, "primitives": [{"attributes": {"POSITION": accessor_index}}]})
        nodes.append({"mesh": index})
    document = {"asset": {"version": "2.0"}, "accessors": accessors, "meshes": meshes, "nodes": nodes}
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    total = 12 + 8 + len(payload)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(payload), 0x4E4F534A) + payload)


def _scene(vertex_counts: list[int], roles: list[str] | None = None):
    diagnostics = []
    role_values = roles or ["paint"] * len(vertex_counts)
    for index, (count, role) in enumerate(zip(vertex_counts, role_values)):
        diagnostics.append({"mesh_index": index, "primitive_index": 0, "declared_role": role})
    return SimpleNamespace(
        positions=np.zeros((sum(vertex_counts), 3), dtype=np.float32),
        primitive_diagnostics=tuple(diagnostics),
    )


def _record(material_hash: int, rgba=(128, 64, 32, 255), *, enabled=True, selector=0xFFFFFFFF):
    return {
        "material_identifier_u64_le": material_hash,
        "primary_color_enabled": bool(enabled),
        "primary_rgba": list(rgba),
        "manufacturer_color_selector": selector,
        "finish_code": 1,
    }


def _report(records):
    return {"status": "paint_descriptor_parsed", "records": list(records)}


class LiveryPaintBindingTests(unittest.TestCase):
    def test_exact_hash_custom_primary_applies_only_to_matching_primitive(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(f"0x{BODY:016X}", 3), (f"0x{HOOD:016X}", 2)])
            scene = _scene([3, 2])
            aux = np.full((5, 4), -1.0, dtype=np.float32)
            aux[:, 0] = 0.0
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY)])
            )
            expected = np.power(np.asarray([128, 64, 32], dtype=np.float32) / 255.0, 2.2)
            np.testing.assert_allclose(rendered[:3, 1:4], np.repeat(expected[None, :], 3, axis=0), atol=1e-6)
            np.testing.assert_allclose(rendered[3:, 1:4], -1.0, atol=1e-6)
            self.assertEqual(diagnostic["status"], "exact_custom_primary_applied")
            self.assertEqual(diagnostic["matched_primitives"], 1)
            self.assertEqual(diagnostic["matched_vertices"], 3)
            self.assertIn(f"0x{HOOD:016X}", diagnostic["unmatched_paint_hashes"])

    def test_same_hash_on_non_paint_primitive_is_not_recolored(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(f"0x{BODY:016X}", 3)])
            scene = _scene([3], roles=["trim"])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY)])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertFalse(diagnostic["rendering_applied"])

    def test_binding_must_be_canonical_64_bit_hash_not_material_name(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [("BodyPaint", 3), ("0x1234", 2)])
            scene = _scene([3, 2])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 5, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY)])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(len(diagnostic["malformed_binding_primitives"]), 2)

    def test_duplicate_c_livery_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(f"0x{BODY:016X}", 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY), _record(BODY, rgba=(1, 2, 3, 255))])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["ambiguous_record_count"], 1)
            self.assertTrue(any("Duplicate C_livery material identifiers" in issue for issue in diagnostic["issues"]))

    def test_manufacturer_selector_is_deferred_not_guessed_from_raw_bgra(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(f"0x{BODY:016X}", 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY, selector=7)])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["deferred_manufacturer_hashes"], [f"0x{BODY:016X}"])
            self.assertFalse(diagnostic["rendering_applied"])

    def test_disabled_primary_color_is_not_applied(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(f"0x{BODY:016X}", 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY, enabled=False)])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["disabled_primary_hashes"], [f"0x{BODY:016X}"])

    def test_unresolved_provenance_keeps_existing_material_aux_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(f"0x{BODY:016X}", 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, {"status": "paint_header_unresolved", "records": []}
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["status"], "paint_binding_unavailable")


if __name__ == "__main__":
    unittest.main()
