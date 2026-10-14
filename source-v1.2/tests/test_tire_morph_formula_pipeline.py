from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import unittest
import zipfile

from fh6garage.preview3d.tire_morph_formula_pipeline import (
    TireMorphFormulaValidationError,
    validate_stock_tire_morph_formula,
)
from tests.test_tire_morph_geometry import _bundle
from tests.test_wheel_spec import _create_fixture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_game_fixture(root: Path) -> tuple[Path, Path]:
    cars = root / "Content" / "media" / "cars"
    tires = cars / "_library" / "scene" / "tires"
    tires.mkdir(parents=True)

    # resolve_cars_dir intentionally requires at least one car archive in media/cars.
    with zipfile.ZipFile(cars / "car_fixture.zip", "w") as archive:
        archive.writestr("placeholder.txt", "read-only fixture")

    tire_archive = tires / "tire_street.zip"
    modelbin = _bundle()
    with zipfile.ZipFile(tire_archive, "w") as archive:
        archive.writestr("tireL_street.modelbin", modelbin)
        archive.writestr("tireR_street.modelbin", modelbin)

    database = root / "fh6.sqlite"
    _create_fixture(database)
    return database, tire_archive


class TireMorphFormulaPipelineTests(unittest.TestCase):
    def test_one_click_stock_pipeline_preserves_db_and_tire_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, tire_archive = _create_game_fixture(root)
            db_before = _sha256(database)
            tire_before = _sha256(tire_archive)

            report = validate_stock_tire_morph_formula(root, database, 1006)

            self.assertEqual(_sha256(database), db_before)
            self.assertEqual(_sha256(tire_archive), tire_before)

        self.assertTrue(report.database_read_only_unchanged)
        self.assertTrue(report.archive_read_only_unchanged)
        self.assertEqual(report.car_spec.car_id, 1006)
        self.assertEqual(report.car_spec.mode, "stock")
        self.assertEqual(report.car_spec.tire_model_name, "Street")
        self.assertTrue(report.archive_path.casefold().endswith("tire_street.zip"))
        self.assertFalse(report.evidence.production_mapping_enabled)
        # The synthetic morph fixture intentionally does not resemble a real tire:
        # selector0 is X-dominant, so the pipeline must fail closed rather than
        # promote the historical formula.
        self.assertEqual(
            report.evidence.complete_mapping_status,
            "diagnostic_only_not_corroborated",
        )
        self.assertTrue(report.stock_geometry.archive_read_only_unchanged)
        self.assertEqual(report.stock_geometry.archive_sha256, report.archive_sha256)
        self.assertFalse(report.stock_geometry.production_mapping_enabled)
        # Width scaling happens to match the synthetic 1 m X span, but Y/Z radial
        # dimensions do not. A partial dimensional match must still fail closed.
        self.assertAlmostEqual(
            report.stock_geometry.front.modelbins[0].reconstructed_width_mm,
            report.car_spec.front.tire_width_mm,
            places=6,
        )
        self.assertEqual(
            report.stock_geometry.complete_mapping_status,
            "diagnostic_stock_dimensions_not_corroborated",
        )

    def test_missing_exact_tire_archive_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, tire_archive = _create_game_fixture(root)
            tire_archive.unlink()
            with self.assertRaises(TireMorphFormulaValidationError):
                validate_stock_tire_morph_formula(root, database, 1006)

    def test_invalid_car_id_fails_before_source_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, tire_archive = _create_game_fixture(root)
            db_before = _sha256(database)
            tire_before = _sha256(tire_archive)
            with self.assertRaisesRegex(TireMorphFormulaValidationError, "positive"):
                validate_stock_tire_morph_formula(root, database, 0)
            self.assertEqual(_sha256(database), db_before)
            self.assertEqual(_sha256(tire_archive), tire_before)


if __name__ == "__main__":
    unittest.main()
