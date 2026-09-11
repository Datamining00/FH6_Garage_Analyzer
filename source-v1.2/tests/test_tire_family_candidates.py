from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.tire_family_candidates import (
    TireFamilyCandidateError,
    select_stock_tire_family_candidates,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root: Path) -> tuple[Path, Path]:
    cars = root / "cars"
    tires = cars / "_library" / "scene" / "tires"
    tires.mkdir(parents=True)
    (cars / "CAR_A.zip").write_bytes(b"car")
    for name in ("Street", "Sport", "Slick"):
        (tires / f"tire_{name}.zip").write_bytes(name.encode("ascii"))

    db = root / "fh6.sqlite"
    connection = sqlite3.connect(db)
    try:
        connection.executescript(
            """
            CREATE TABLE Data_Car (
                Id INTEGER PRIMARY KEY,
                FrontTireWidthMM REAL,
                RearTireWidthMM REAL,
                FrontTireAspect REAL,
                RearTireAspect REAL,
                FrontWheelDiameterIN REAL,
                RearWheelDiameterIN REAL
            );
            CREATE TABLE List_UpgradeTireCompound (
                Id INTEGER PRIMARY KEY,
                Ordinal INTEGER,
                IsStock INTEGER,
                TireCompoundID INTEGER,
                TireModelName TEXT
            );
            INSERT INTO Data_Car VALUES (1001, 205, 205, 55, 55, 16, 16);
            INSERT INTO Data_Car VALUES (1002, 225, 245, 45, 40, 18, 18);
            INSERT INTO Data_Car VALUES (1003, 245, 345, 35, 35, 19, 19);
            INSERT INTO List_UpgradeTireCompound VALUES (1, 1001, 1, 1, 'Street');
            INSERT INTO List_UpgradeTireCompound VALUES (2, 1002, 1, 2, 'Sport');
            INSERT INTO List_UpgradeTireCompound VALUES (3, 1003, 1, 3, 'Slick');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return cars, db


class TireFamilyCandidateTests(unittest.TestCase):
    def test_selects_distinct_exact_stock_families_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            cars, db = _fixture(Path(directory))
            before = _sha256(db)
            report = select_stock_tire_family_candidates(
                cars, db, exclude_model_names=("Slick",), limit=5
            )
            after = _sha256(db)

        self.assertEqual(before, after)
        self.assertTrue(report.database_read_only_unchanged)
        self.assertEqual(report.complete_mapping_status, "diagnostic_family_candidates_ready")
        self.assertFalse(report.production_mapping_enabled)
        self.assertEqual(report.candidate_family_count, 2)
        self.assertEqual(
            [item.tire_model_name for item in report.candidates],
            ["Sport", "Street"],
        )
        self.assertEqual(
            [item.car_id for item in report.candidates],
            [1002, 1001],
        )

    def test_limit_one_is_not_cross_family_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            cars, db = _fixture(Path(directory))
            report = select_stock_tire_family_candidates(cars, db, limit=1)

        self.assertEqual(report.candidate_family_count, 1)
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_family_candidates_insufficient",
        )

    def test_nonpositive_limit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cars, db = _fixture(Path(directory))
            with self.assertRaises(TireFamilyCandidateError):
                select_stock_tire_family_candidates(cars, db, limit=0)


if __name__ == "__main__":
    unittest.main()
