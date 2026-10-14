from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path
import unittest
import zipfile

from fh6garage.preview3d.tire_morph_cross_family_validation import (
    TireMorphCrossFamilyValidationError,
    validate_stock_tire_morph_families,
)
from tests.test_tire_morph_geometry import _bundle
from tests.test_wheel_spec import _create_fixture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_cross_family_fixture(root: Path) -> tuple[Path, tuple[Path, Path]]:
    cars = root / "Content" / "media" / "cars"
    tires = cars / "_library" / "scene" / "tires"
    tires.mkdir(parents=True)

    with zipfile.ZipFile(cars / "car_fixture.zip", "w") as archive:
        archive.writestr("placeholder.txt", "read-only fixture")

    database = root / "fh6.sqlite"
    _create_fixture(database)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            INSERT INTO Data_Car VALUES (1229, 225, 255, 40, 35, 18, 18, 703);
            INSERT INTO List_UpgradeCarBody VALUES (2, 1229, 1, 343003);
            INSERT INTO List_UpgradeTireCompound VALUES (802, 1229, 1, 2, 'Sport');
            INSERT INTO List_Wheels VALUES (703, 'SECOND_stock');
            """
        )
        connection.commit()
    finally:
        connection.close()

    street = tires / "tire_street.zip"
    sport = tires / "tire_sport.zip"
    for archive_path, stem in ((street, "street"), (sport, "sport")):
        modelbin = _bundle()
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(f"tireL_{stem}.modelbin", modelbin)
            archive.writestr(f"tireR_{stem}.modelbin", modelbin)
    return database, (street, sport)


class TireMorphCrossFamilyValidationTests(unittest.TestCase):
    def test_two_distinct_tire_model_names_are_validated_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, archives = _create_cross_family_fixture(root)
            db_before = _sha256(database)
            archive_before = tuple(_sha256(path) for path in archives)

            report = validate_stock_tire_morph_families(
                root,
                database,
                (1006, 1229),
            )

            self.assertEqual(_sha256(database), db_before)
            self.assertEqual(
                tuple(_sha256(path) for path in archives),
                archive_before,
            )

        self.assertEqual(report.requested_car_ids, (1006, 1229))
        self.assertEqual(report.unique_tire_model_names, ("Street", "Sport"))
        self.assertEqual(report.unique_family_count, 2)
        self.assertTrue(report.enough_unique_families)
        self.assertFalse(report.production_mapping_enabled)
        # Synthetic geometry intentionally does not reproduce real tire radial
        # deformation, so cross-family evidence must remain fail-closed.
        self.assertFalse(report.all_formula_roles_corroborated)
        self.assertFalse(report.all_stock_geometry_corroborated)
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_cross_family_not_corroborated",
        )
        self.assertTrue(report.reports[0].archive_path.casefold().endswith("tire_street.zip"))
        self.assertTrue(report.reports[1].archive_path.casefold().endswith("tire_sport.zip"))

    def test_two_cars_with_same_tire_model_do_not_count_as_cross_family(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, _archives = _create_cross_family_fixture(root)
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "UPDATE List_UpgradeTireCompound SET TireModelName = 'Street' WHERE Ordinal = 1229 AND IsStock = 1"
                )
                connection.commit()
            finally:
                connection.close()

            report = validate_stock_tire_morph_families(
                root,
                database,
                (1006, 1229),
            )

        self.assertEqual(report.unique_tire_model_names, ("Street",))
        self.assertEqual(report.unique_family_count, 1)
        self.assertFalse(report.enough_unique_families)
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_cross_family_insufficient_unique_families",
        )
        self.assertFalse(report.production_mapping_enabled)

    def test_duplicate_car_ids_fail_before_validation(self) -> None:
        with self.assertRaisesRegex(
            TireMorphCrossFamilyValidationError,
            "duplicate car_ids",
        ):
            validate_stock_tire_morph_families(
                Path("unused"),
                Path("unused.sqlite"),
                (1006, 1006),
            )

    def test_fewer_car_ids_than_required_families_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            TireMorphCrossFamilyValidationError,
            "at least 2 distinct car_ids",
        ):
            validate_stock_tire_morph_families(
                Path("unused"),
                Path("unused.sqlite"),
                (1006,),
            )


if __name__ == "__main__":
    unittest.main()
