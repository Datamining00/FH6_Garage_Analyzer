from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.manufacturer_overlay_diagnostics import (
    build_manufacturer_overlay_diagnostics,
)


BODY = 0xF7DBE8A7C839A675
HOOD = 0x6AC1E9D87FE5D953


def _write_glb(
    path: Path,
    *,
    binding: int = BODY,
    material_name: str = "carpaint",
    uv4: str = "valid",
) -> None:
    accessors = [
        {"componentType": 5126, "count": 3, "type": "VEC3"},
    ]
    attrs = {"POSITION": 0}
    if uv4 == "valid":
        accessors.append({"componentType": 5126, "count": 3, "type": "VEC2"})
        attrs["TEXCOORD_4"] = 1
    elif uv4 == "bad_type":
        accessors.append({"componentType": 5126, "count": 3, "type": "VEC3"})
        attrs["TEXCOORD_4"] = 1
    elif uv4 == "bad_count":
        accessors.append({"componentType": 5126, "count": 2, "type": "VEC2"})
        attrs["TEXCOORD_4"] = 1

    document = {
        "asset": {"version": "2.0"},
        "accessors": accessors,
        "meshes": [
            {
                "name": "BodyPaintMesh",
                "extras": {
                    "kfps_role": "paint",
                    "kfps_material_binding_hash": f"{binding:016X}",
                    "kfps_material_name": material_name,
                },
                "primitives": [{"attributes": attrs}],
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


def _record(
    material_hash: int,
    *,
    selector: int = 0,
    primary_enabled: bool = False,
) -> dict:
    return {
        "material_identifier_u64_le": material_hash,
        "manufacturer_color_selector": selector,
        "primary_color_enabled": primary_enabled,
        "primary_rgba": [128, 64, 32, 255],
        "secondary_color_enabled": False,
        "secondary_rgba": [0, 0, 0, 0],
        "finish_code": 1,
    }


def _paint(records: list[dict]) -> dict:
    return {"status": "paint_descriptor_parsed", "records": records}


def _palette(entries: list[dict]) -> dict:
    return {
        "status": "manufacturer_colors_parsed",
        "groups": [
            {
                "index": 0,
                "entry_count": len(entries),
                "entries": entries,
                "primary_group_preview_present": True,
                "primary_group_preview_color": [0.2, 0.4, 0.6],
                "secondary_group_preview_present": False,
                "secondary_group_preview_color": [0.0, 0.0, 0.0],
            }
        ],
    }


def _entry(index: int, *, names=("carpaint",), path="factory.swatchbin") -> dict:
    return {
        "index": index,
        "material_names": list(names),
        "preview_color": [0.1, 0.2, 0.3],
        "path": path,
    }


class ManufacturerOverlayDiagnosticsTests(unittest.TestCase):
    def test_unique_exact_material_name_and_uv4_are_diagnosed_but_not_rendered(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, material_name="CarPaint", uv4="valid")
            report = build_manufacturer_overlay_diagnostics(
                glb,
                _paint([_record(BODY, selector=0, primary_enabled=False)]),
                _palette([_entry(0, names=("carpaint",), path="factory.swatchbin")]),
            )

            self.assertEqual(report["status"], "manufacturer_overlay_candidates_diagnosed")
            self.assertEqual(report["exact_candidate_count"], 1)
            self.assertFalse(report["rendering_enabled"])
            self.assertFalse(report["rendering_applied"])
            row = report["candidates"][0]
            self.assertEqual(row["status"], "exact_manufacturer_overlay_candidate_diagnosed")
            self.assertEqual(row["entry_index"], 0)
            self.assertEqual(row["entry_path"], "factory.swatchbin")
            self.assertEqual(row["uv4"]["status"], "uv4_exact_kfps_accessor")
            self.assertEqual(row["uv4"]["count"], 3)
            self.assertEqual(row["uv4"]["position_count"], 3)

    def test_material_name_matching_does_not_use_substring_or_path_guessing(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, material_name="carpaint_secondary", uv4="valid")
            report = build_manufacturer_overlay_diagnostics(
                glb,
                _paint([_record(BODY)]),
                _palette([_entry(0, names=("carpaint",), path="carpaint_secondary.swatchbin")]),
            )

            self.assertEqual(report["exact_candidate_count"], 0)
            self.assertEqual(report["unmatched_entry_count"], 1)
            self.assertEqual(
                report["candidates"][0]["status"],
                "manufacturer_entry_not_targeted_by_exact_material_name",
            )

    def test_duplicate_exact_material_name_entries_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, material_name="carpaint", uv4="valid")
            report = build_manufacturer_overlay_diagnostics(
                glb,
                _paint([_record(BODY)]),
                _palette([
                    _entry(0, names=("carpaint",), path="a.swatchbin"),
                    _entry(1, names=("CARPAINT",), path="b.swatchbin"),
                ]),
            )

            self.assertEqual(report["exact_candidate_count"], 0)
            self.assertEqual(report["ambiguous_entry_count"], 1)
            row = report["candidates"][0]
            self.assertEqual(row["status"], "manufacturer_entry_material_name_ambiguous")
            self.assertEqual(row["matching_entry_indices"], [0, 1])

    def test_uv4_must_be_exact_float_vec2_with_position_count_match(self):
        for uv4_mode in ("missing", "bad_type", "bad_count"):
            with self.subTest(uv4_mode=uv4_mode), tempfile.TemporaryDirectory() as temp:
                glb = Path(temp) / "car.glb"
                _write_glb(glb, uv4=uv4_mode)
                report = build_manufacturer_overlay_diagnostics(
                    glb,
                    _paint([_record(BODY)]),
                    _palette([_entry(0)]),
                )
                self.assertEqual(report["exact_candidate_count"], 0)
                self.assertEqual(report["missing_or_invalid_uv4_count"], 1)
                self.assertNotEqual(
                    report["candidates"][0]["uv4"]["status"],
                    "uv4_exact_kfps_accessor",
                )

    def test_any_explicit_custom_primary_suppresses_manufacturer_overlay_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(glb, binding=HOOD, material_name="carpaint", uv4="valid")
            report = build_manufacturer_overlay_diagnostics(
                glb,
                _paint([
                    _record(BODY, selector=0xFFFFFFFF, primary_enabled=True),
                    _record(HOOD, selector=0, primary_enabled=False),
                ]),
                _palette([_entry(0)]),
            )

            self.assertTrue(report["global_custom_primary_active"])
            self.assertEqual(report["globally_suppressed_count"], 1)
            self.assertEqual(report["exact_candidate_count"], 0)
            self.assertEqual(
                report["candidates"][0]["status"],
                "manufacturer_overlay_suppressed_by_global_custom_paint",
            )


if __name__ == "__main__":
    unittest.main()
