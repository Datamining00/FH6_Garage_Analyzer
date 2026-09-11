from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from fh6garage.preview3d.exact_game_asset import resolve_exact_game_asset_reference


class ExactGameAssetTests(unittest.TestCase):
    def test_arbitrary_materialbin_bytes_resolve_from_exact_loose_path_without_swatch_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            cars = root / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "CAR_TEST.zip"
            with zipfile.ZipFile(vehicle, "w"):
                pass
            source = root / "media" / "shared" / "paint.materialbin"
            source.parent.mkdir(parents=True)
            payload = b"not-a-swatchbin-material-payload"
            source.write_bytes(payload)

            result = resolve_exact_game_asset_reference(
                "media/shared/paint.materialbin", vehicle, Path(temp) / "cache"
            )
            self.assertEqual(result.status, "resolved_payload")
            self.assertEqual(result.resolution_mode, "game_loose_exact")
            self.assertEqual(result.payload_size, len(payload))
            self.assertTrue(Path(result.cache_path or "").is_file())
            self.assertEqual(Path(result.cache_path or "").read_bytes(), payload)

    def test_vehicle_archive_exact_preserves_arbitrary_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            cars = root / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "CAR_TEST.zip"
            payload = b"materialbin-in-vehicle-archive"
            with zipfile.ZipFile(vehicle, "w") as archive:
                archive.writestr("materials/body.materialbin", payload)

            result = resolve_exact_game_asset_reference(
                "media/cars/CAR_TEST/materials/body.materialbin",
                vehicle,
                Path(temp) / "cache",
            )
            self.assertEqual(result.status, "resolved_payload")
            self.assertEqual(result.resolution_mode, "vehicle_archive_exact")
            self.assertEqual(result.archive_entry, "materials/body.materialbin")
            self.assertEqual(Path(result.cache_path or "").read_bytes(), payload)

    def test_derived_zip_exact_is_allowed_but_filename_fallback_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            cars = root / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "CAR_TEST.zip"
            with zipfile.ZipFile(vehicle, "w"):
                pass
            archive_path = root / "media" / "shared" / "materials.zip"
            archive_path.parent.mkdir(parents=True)
            payload = b"derived-materialbin"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("body.materialbin", payload)

            exact = resolve_exact_game_asset_reference(
                "media/shared/materials/body.materialbin",
                vehicle,
                Path(temp) / "cache",
            )
            self.assertEqual(exact.status, "resolved_payload")
            self.assertEqual(exact.resolution_mode, "derived_zip_exact")

            fallback = resolve_exact_game_asset_reference(
                "body.materialbin", vehicle, Path(temp) / "cache2"
            )
            self.assertEqual(fallback.status, "reference_unresolved")
            self.assertEqual(fallback.resolution_mode, "none")

    def test_parent_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            vehicle = Path(temp) / "game" / "media" / "cars" / "CAR_TEST.zip"
            vehicle.parent.mkdir(parents=True)
            with zipfile.ZipFile(vehicle, "w"):
                pass
            result = resolve_exact_game_asset_reference(
                "../paint.materialbin", vehicle, Path(temp) / "cache"
            )
            self.assertEqual(result.status, "reference_invalid")
            self.assertEqual(result.normalized_path, "")


if __name__ == "__main__":
    unittest.main()
