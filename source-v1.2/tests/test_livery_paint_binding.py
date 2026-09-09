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


def _binding(material_hash: int) -> str:
    # Exact pinned KFPS GlbWriter contract: MaterialBindingHash.ToString("X16").
    return f"{material_hash:016X}"


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


def _palette(
    primary=(0.2, 0.4, 0.6),
    *,
    primary_present=True,
    secondary=(0.7, 0.8, 0.9),
    secondary_present=True,
    entry_count=1,
):
    entries = [
        {"index": index, "material_names": ["carpaint"], "preview_color": [0.1, 0.1, 0.1], "path": f"p{index}.swatchbin"}
        for index in range(entry_count)
    ]
    return {
        "status": "manufacturer_colors_parsed",
        "groups": [
            {
                "index": 0,
                "entry_count": entry_count,
                "entries": entries,
                "primary_group_preview_present": bool(primary_present),
                "primary_group_preview_color": list(primary),
                "secondary_group_preview_present": bool(secondary_present),
                "secondary_group_preview_color": list(secondary),
            }
        ],
    }


class LiveryPaintBindingTests(unittest.TestCase):
    def test_exact_kfps_x16_hash_custom_primary_applies_only_to_matching_primitive(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3), (_binding(HOOD), 2)])
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
            self.assertEqual(diagnostic["binding_format"], "kfps_material_binding_hash_x16_unprefixed")
            self.assertEqual(diagnostic["matched_primitives"], 1)
            self.assertEqual(diagnostic["matched_custom_primitives"], 1)
            self.assertEqual(diagnostic["matched_manufacturer_primitives"], 0)
            self.assertEqual(diagnostic["matched_vertices"], 3)
            self.assertIn(f"0x{HOOD:016X}", diagnostic["unmatched_paint_hashes"])

    def test_manufacturer_selector_applies_group_trailer_primary_as_linear_even_if_custom_primary_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb,
                scene,
                aux,
                _report([_record(BODY, rgba=(255, 0, 255, 255), enabled=False, selector=0)]),
                _palette(primary=(0.2, 0.4, 0.6)),
            )
            expected = np.asarray([0.2, 0.4, 0.6], dtype=np.float32)
            np.testing.assert_allclose(rendered[:, 1:4], np.repeat(expected[None, :], 3, axis=0), atol=1e-6)
            self.assertEqual(diagnostic["status"], "exact_manufacturer_primary_applied")
            self.assertEqual(diagnostic["matched_manufacturer_primitives"], 1)
            self.assertEqual(diagnostic["matched_custom_primitives"], 0)
            self.assertEqual(diagnostic["manufacturer_matched_hashes"], [f"0x{BODY:016X}"])
            self.assertEqual(diagnostic["manufacturer_overridden_hashes"], [])
            self.assertEqual(diagnostic["disabled_primary_hashes"], [])
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["status"], "manufacturer_primary_linear_resolved")
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["primary_output"], "manufacturer_group_trailer")
            self.assertTrue(diagnostic["manufacturer_selector_results"][0]["secondary_enabled"])

    def test_enabled_custom_primary_overrides_manufacturer_group_primary(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb,
                scene,
                aux,
                _report([_record(BODY, rgba=(200, 100, 50, 255), enabled=True, selector=0)]),
                _palette(primary=(0.2, 0.4, 0.6)),
            )
            expected = np.power(np.asarray([200, 100, 50], dtype=np.float32) / 255.0, 2.2)
            np.testing.assert_allclose(rendered[:, 1:4], np.repeat(expected[None, :], 3, axis=0), atol=1e-6)
            self.assertEqual(diagnostic["status"], "exact_custom_primary_applied")
            self.assertEqual(diagnostic["matched_custom_primitives"], 1)
            self.assertEqual(diagnostic["matched_manufacturer_primitives"], 0)
            self.assertEqual(diagnostic["manufacturer_matched_hashes"], [])
            self.assertEqual(diagnostic["manufacturer_overridden_hashes"], [f"0x{BODY:016X}"])
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["status"], "manufacturer_primary_linear_resolved")
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["primary_output"], "custom_primary_override")

    def test_manufacturer_group_primary_is_group_level_even_when_group_has_multiple_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 2)])
            scene = _scene([2])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 2, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb,
                scene,
                aux,
                _report([_record(BODY, enabled=False, selector=0)]),
                _palette(primary=(0.15, 0.25, 0.35), entry_count=2),
            )
            np.testing.assert_allclose(rendered[:, 1:4], [[0.15, 0.25, 0.35]] * 2, atol=1e-6)
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["entry_count"], 2)
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["primary_output"], "manufacturer_group_trailer")
            self.assertEqual(diagnostic["matched_manufacturer_primitives"], 1)

    def test_manufacturer_selector_without_palette_is_deferred_and_never_uses_raw_bgra(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY, rgba=(255, 0, 255, 255), enabled=False, selector=7)])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["deferred_manufacturer_hashes"], [f"0x{BODY:016X}"])
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["status"], "manufacturer_palette_unavailable")
            self.assertFalse(diagnostic["rendering_applied"])

    def test_manufacturer_primary_absent_fails_closed_without_custom_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb,
                scene,
                aux,
                _report([_record(BODY, rgba=(255, 255, 255, 255), enabled=False, selector=0)]),
                _palette(primary_present=False),
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["deferred_manufacturer_hashes"], [f"0x{BODY:016X}"])
            self.assertEqual(diagnostic["manufacturer_selector_results"][0]["status"], "manufacturer_primary_trailer_absent")
            self.assertFalse(diagnostic["rendering_applied"])

    def test_same_hash_on_non_paint_primitive_is_not_recolored(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3)])
            scene = _scene([3], roles=["trim"])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY)])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertFalse(diagnostic["rendering_applied"])

    def test_binding_must_be_exact_unprefixed_kfps_x16_not_material_name_or_short_hex(self):
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

    def test_human_readable_0x_prefix_is_rejected_because_kfps_exporter_does_not_emit_it(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(f"0x{BODY:016X}", 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY)])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(len(diagnostic["malformed_binding_primitives"]), 1)
            self.assertFalse(diagnostic["rendering_applied"])

    def test_duplicate_c_livery_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, _report([_record(BODY), _record(BODY, rgba=(1, 2, 3, 255))])
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["ambiguous_record_count"], 1)
            self.assertTrue(any("Duplicate C_livery material identifiers" in issue for issue in diagnostic["issues"]))

    def test_disabled_custom_primary_color_is_not_applied(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [(_binding(BODY), 3)])
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
            _write_glb(glb, [(_binding(BODY), 3)])
            scene = _scene([3])
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, {"status": "paint_header_unresolved", "records": []}
            )
            np.testing.assert_array_equal(rendered, aux)
            self.assertEqual(diagnostic["status"], "paint_binding_unavailable")


if __name__ == "__main__":
    unittest.main()
