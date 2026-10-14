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


def _write_glb(path: Path) -> None:
    document = {
        "asset": {"version": "2.0"},
        "accessors": [{"count": 3}],
        "meshes": [
            {
                "extras": {
                    "kfps_role": "paint",
                    "kfps_material_binding_hash": f"{HOOD:016X}",
                },
                "primitives": [{"attributes": {"POSITION": 0}}],
            }
        ],
        "nodes": [{"mesh": 0}],
    }
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    total = 12 + 8 + len(payload)
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, total)
        + struct.pack("<II", len(payload), 0x4E4F534A)
        + payload
    )


def _record(material_hash: int, *, enabled: bool, selector: int, rgba=(128, 64, 32, 255)) -> dict:
    return {
        "material_identifier_u64_le": material_hash,
        "primary_color_enabled": enabled,
        "primary_rgba": list(rgba),
        "manufacturer_color_selector": selector,
        "finish_code": 1,
    }


def _palette() -> dict:
    return {
        "status": "manufacturer_colors_parsed",
        "groups": [
            {
                "index": 0,
                "entry_count": 1,
                "entries": [
                    {
                        "index": 0,
                        "material_names": ["carpaint"],
                        "preview_color": [0.1, 0.1, 0.1],
                        "path": "factory.swatchbin",
                    }
                ],
                "primary_group_preview_present": True,
                "primary_group_preview_color": [0.95, 0.8, 0.1],
                "secondary_group_preview_present": False,
                "secondary_group_preview_color": [0.0, 0.0, 0.0],
            }
        ],
    }


class LiveryPaintBindingGlobalGateTests(unittest.TestCase):
    def test_ambiguous_enabled_record_still_suppresses_manufacturer_paint_globally(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb)
            scene = SimpleNamespace(
                positions=np.zeros((3, 3), dtype=np.float32),
                primitive_diagnostics=(
                    {"mesh_index": 0, "primitive_index": 0, "declared_role": "paint"},
                ),
            )
            aux = np.asarray([[0.0, -1.0, -1.0, -1.0]] * 3, dtype=np.float32)
            report = {
                "status": "paint_descriptor_parsed",
                "records": [
                    _record(BODY, enabled=True, selector=0xFFFFFFFF),
                    _record(BODY, enabled=True, selector=0xFFFFFFFF, rgba=(10, 20, 30, 255)),
                    _record(HOOD, enabled=False, selector=0, rgba=(0, 0, 0, 0)),
                ],
            }

            rendered, diagnostic = apply_exact_livery_paint_to_aux_stream(
                glb, scene, aux, report, _palette()
            )

            np.testing.assert_array_equal(rendered, aux)
            self.assertTrue(diagnostic["global_custom_primary_active"])
            self.assertEqual(diagnostic["ambiguous_record_count"], 1)
            self.assertEqual(
                diagnostic["manufacturer_global_gate"],
                "suppressed_by_explicit_custom_primary",
            )
            self.assertEqual(
                diagnostic["manufacturer_globally_suppressed_hashes"],
                [f"0x{HOOD:016X}"],
            )
            self.assertFalse(diagnostic["rendering_applied"])


if __name__ == "__main__":
    unittest.main()
