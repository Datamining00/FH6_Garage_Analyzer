from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from fh6garage.preview3d.manufacturer_overlay_texture_diagnostics import (
    resolve_manufacturer_overlay_payloads,
)


def _p3d(path: str) -> dict:
    return {
        "status": "manufacturer_overlay_candidates_diagnosed",
        "exact_candidate_count": 1,
        "candidates": [
            {
                "mesh_index": 1,
                "primitive_index": 0,
                "material_hash": "0xF7DBE8A7C839A675",
                "material_name": "carpaint",
                "selector": 0,
                "group_index": 0,
                "entry_index": 0,
                "entry_path": path,
                "uv4": {"status": "uv4_exact_kfps_accessor"},
                "status": "exact_manufacturer_overlay_candidate_diagnosed",
            }
        ],
    }


def _swatch_payload() -> bytes:
    # Resolver-stage contract only: valid native swatch payload begins with Grub.
    return (0x47727562).to_bytes(4, "little") + b"\x00" * 28


class ManufacturerOverlayTextureDiagnosticsTests(unittest.TestCase):
    def test_exact_game_loose_path_is_promoted_without_rendering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            cars = root / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "CAR_TEST.zip"
            with zipfile.ZipFile(vehicle, "w"):
                pass
            texture = root / "media" / "shared" / "factory.swatchbin"
            texture.parent.mkdir(parents=True)
            texture.write_bytes(_swatch_payload())
            cache = Path(temp) / "cache"

            report = resolve_manufacturer_overlay_payloads(
                _p3d("media/shared/factory.swatchbin"), vehicle, cache
            )

            self.assertEqual(report["status"], "manufacturer_overlay_texture_payloads_diagnosed")
            self.assertEqual(report["candidate_count"], 1)
            self.assertEqual(report["exact_resolved_count"], 1)
            self.assertEqual(report["fallback_deferred_count"], 0)
            self.assertEqual(report["unresolved_count"], 0)
            row = report["payloads"][0]
            self.assertEqual(row["status"], "manufacturer_overlay_payload_resolved_exact")
            self.assertTrue(row["exact_resolution_approved"])
            self.assertEqual(row["payload"]["resolution_mode"], "game_loose_exact")
            self.assertEqual(row["payload"]["status"], "resolved_payload")
            self.assertTrue(Path(row["payload"]["cache_path"]).is_file())
            self.assertFalse(row["rendering_enabled"])
            self.assertFalse(report["rendering_applied"])
            self.assertFalse(report["game_data_modified"])

    def test_unique_filename_fallback_is_preserved_but_not_promoted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            cars = root / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "CAR_TEST.zip"
            with zipfile.ZipFile(vehicle, "w"):
                pass
            texture_zip = root / "media" / "shared" / "textures.zip"
            texture_zip.parent.mkdir(parents=True)
            with zipfile.ZipFile(texture_zip, "w") as archive:
                archive.writestr("textures/factory.swatchbin", _swatch_payload())

            report = resolve_manufacturer_overlay_payloads(
                _p3d("factory.swatchbin"), vehicle, Path(temp) / "cache"
            )

            self.assertEqual(report["exact_resolved_count"], 0)
            self.assertEqual(report["fallback_deferred_count"], 1)
            row = report["payloads"][0]
            self.assertEqual(row["status"], "manufacturer_overlay_payload_fallback_deferred")
            self.assertFalse(row["exact_resolution_approved"])
            self.assertEqual(row["payload"]["resolution_mode"], "textures_zip_unique_filename")
            self.assertFalse(report["rendering_enabled"])

    def test_unresolved_payload_remains_deferred(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            cars = root / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "CAR_TEST.zip"
            with zipfile.ZipFile(vehicle, "w"):
                pass

            report = resolve_manufacturer_overlay_payloads(
                _p3d("media/shared/missing.swatchbin"), vehicle, Path(temp) / "cache"
            )

            self.assertEqual(report["exact_resolved_count"], 0)
            self.assertEqual(report["unresolved_count"], 1)
            row = report["payloads"][0]
            self.assertEqual(row["status"], "manufacturer_overlay_payload_unresolved")
            self.assertFalse(row["exact_resolution_approved"])
            self.assertEqual(row["payload"]["status"], "reference_unresolved")

    def test_non_exact_p3d_rows_are_never_resolved(self):
        report = {
            "status": "manufacturer_overlay_candidates_diagnosed",
            "candidates": [
                {
                    "entry_path": "factory.swatchbin",
                    "status": "manufacturer_entry_material_name_ambiguous",
                }
            ],
        }
        result = resolve_manufacturer_overlay_payloads(
            report, "missing-vehicle.zip", "missing-cache"
        )
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["payloads"], [])
        self.assertFalse(result["rendering_enabled"])


if __name__ == "__main__":
    unittest.main()
