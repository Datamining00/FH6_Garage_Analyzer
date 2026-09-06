from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fh6garage.preview3d.wheel_morph_auto import resolve_automatic_stock_rim_morph
from fh6garage.preview3d.wheel_spec_database import WheelSpecDatabaseError


def _database(path: Path, *, media_name: str = "FER_FXX_05", include_car: bool = True) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE Data_Car (
                Id INTEGER PRIMARY KEY,
                MediaName TEXT,
                FrontTireWidthMM REAL,
                FrontTireAspect REAL,
                FrontWheelDiameterIN REAL,
                RearTireWidthMM REAL,
                RearTireAspect REAL,
                RearWheelDiameterIN REAL
            );
            """
        )
        if include_car:
            connection.execute(
                "INSERT INTO Data_Car VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1006, media_name, 245, 35, 19, 345, 35, 19),
            )
        connection.commit()
    finally:
        connection.close()


class AutomaticStockRimMorphTests(unittest.TestCase):
    def test_helper_unavailable_skips_database_without_guessing(self) -> None:
        with patch(
            "fh6garage.preview3d.wheel_morph_auto.verified_bundled_wheel_morph_helper",
            return_value=None,
        ), patch(
            "fh6garage.preview3d.wheel_morph_auto.ensure_stock_wheel_database"
        ) as ensure_db:
            result = resolve_automatic_stock_rim_morph(1006, "FER_FXX_05")
        self.assertEqual(result.status, "helper_unavailable")
        self.assertIsNone(result.weights)
        ensure_db.assert_not_called()

    def test_database_failure_falls_back_without_geometry_guess(self) -> None:
        with patch(
            "fh6garage.preview3d.wheel_morph_auto.verified_bundled_wheel_morph_helper",
            return_value=Path("verified-helper.exe"),
        ), patch(
            "fh6garage.preview3d.wheel_morph_auto.ensure_stock_wheel_database",
            side_effect=WheelSpecDatabaseError("offline"),
        ):
            result = resolve_automatic_stock_rim_morph(1006, "FER_FXX_05")
        self.assertEqual(result.status, "database_unavailable")
        self.assertIsNone(result.weights)
        self.assertIn("offline", result.detail)

    def test_missing_car_falls_back_without_per_car_constants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "db.sqlite"
            _database(database, include_car=False)
            with patch(
                "fh6garage.preview3d.wheel_morph_auto.verified_bundled_wheel_morph_helper",
                return_value=Path("verified-helper.exe"),
            ), patch(
                "fh6garage.preview3d.wheel_morph_auto.ensure_stock_wheel_database",
                return_value=database,
            ):
                result = resolve_automatic_stock_rim_morph(1006, "FER_FXX_05")
        self.assertEqual(result.status, "car_unavailable")
        self.assertIsNone(result.weights)

    def test_media_name_mismatch_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "db.sqlite"
            _database(database, media_name="OTHER_CAR")
            with patch(
                "fh6garage.preview3d.wheel_morph_auto.verified_bundled_wheel_morph_helper",
                return_value=Path("verified-helper.exe"),
            ), patch(
                "fh6garage.preview3d.wheel_morph_auto.ensure_stock_wheel_database",
                return_value=database,
            ):
                result = resolve_automatic_stock_rim_morph(1006, "FER_FXX_05")
        self.assertEqual(result.status, "media_name_mismatch")
        self.assertIsNone(result.weights)
        self.assertIn("OTHER_CAR", result.detail)

    def test_verified_fxx_stock_spec_maps_to_proven_rim_weights(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "db.sqlite"
            _database(database)
            with patch(
                "fh6garage.preview3d.wheel_morph_auto.verified_bundled_wheel_morph_helper",
                return_value=Path("verified-helper.exe"),
            ), patch(
                "fh6garage.preview3d.wheel_morph_auto.ensure_stock_wheel_database",
                return_value=database,
            ):
                result = resolve_automatic_stock_rim_morph(1006, "FER_FXX_05")

        self.assertTrue(result.applied)
        self.assertIsNotNone(result.weights)
        weights = result.weights
        assert weights is not None
        self.assertEqual(weights.car_id, 1006)
        self.assertEqual(weights.wheel_spec_mode, "stock")
        self.assertAlmostEqual(weights.front.diameter_weight, (19 - 10) / 14)
        self.assertAlmostEqual(weights.rear.diameter_weight, (19 - 10) / 14)
        self.assertAlmostEqual(weights.front.width_weight, (1 - 245 / 1000) / 0.9)
        self.assertAlmostEqual(weights.rear.width_weight, (1 - 345 / 1000) / 0.9)
        self.assertEqual(weights.front.scale_x, 1.0)
        self.assertEqual(weights.rear.scale_x, 1.0)
        self.assertIn("245 mm / 19 in", result.detail)
        self.assertIn("345 mm / 19 in", result.detail)


if __name__ == "__main__":
    unittest.main()
