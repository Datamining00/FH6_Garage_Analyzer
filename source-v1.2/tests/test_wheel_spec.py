from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.wheel_spec import (
    FH6WheelSpecResolver,
    WheelSpecError,
    WheelUpgradeSelection,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
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
                RearWheelDiameterIN REAL,
                StockWheelID INTEGER
            );
            CREATE TABLE List_UpgradeCarBody (
                Id INTEGER PRIMARY KEY,
                Ordinal INTEGER,
                IsStock INTEGER,
                CarBodyID INTEGER
            );
            CREATE TABLE List_UpgradeRimSizeFront (
                Id INTEGER PRIMARY KEY,
                Ordinal INTEGER,
                FrontWheelDiameter REAL
            );
            CREATE TABLE List_UpgradeRimSizeRear (
                Id INTEGER PRIMARY KEY,
                Ordinal INTEGER,
                RearWheelDiameter REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireWidthFront (
                Id INTEGER PRIMARY KEY,
                CarBodyID INTEGER,
                FrontTireWidth REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireWidthRear (
                Id INTEGER PRIMARY KEY,
                CarBodyID INTEGER,
                RearTireWidth REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireAspectRatioFront (
                Id INTEGER PRIMARY KEY,
                CarBodyID INTEGER,
                FrontTireAspectRatioOffset REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireAspectRatioRear (
                Id INTEGER PRIMARY KEY,
                CarBodyID INTEGER,
                RearTireAspectRatioOffset REAL
            );
            CREATE TABLE List_UpgradeTireCompound (
                Id INTEGER PRIMARY KEY,
                Ordinal INTEGER,
                IsStock INTEGER,
                TireCompoundID INTEGER,
                TireModelName TEXT
            );
            CREATE TABLE List_Wheels (
                ID INTEGER PRIMARY KEY,
                MediaName TEXT
            );

            INSERT INTO Data_Car VALUES (1006, 255, 335, 35, 30, 19, 20, 700);
            INSERT INTO List_UpgradeCarBody VALUES (1, 1006, 1, 343002);

            INSERT INTO List_UpgradeRimSizeFront VALUES (110, 1006, 20);
            INSERT INTO List_UpgradeRimSizeRear VALUES (111, 1006, 21);
            INSERT INTO List_UpgradeRimSizeFront VALUES (999, 2000, 24);

            INSERT INTO List_UpgradeCarBodyTireWidthFront VALUES (120, 343002, 265);
            INSERT INTO List_UpgradeCarBodyTireWidthRear VALUES (121, 343002, 345);
            INSERT INTO List_UpgradeCarBodyTireAspectRatioFront VALUES (130, 343002, -5);
            INSERT INTO List_UpgradeCarBodyTireAspectRatioRear VALUES (131, 343002, 2);

            INSERT INTO List_UpgradeTireCompound VALUES (800, 1006, 1, 1, 'Street');
            INSERT INTO List_UpgradeTireCompound VALUES (801, 1006, 0, 7, 'Semi_Slick');

            INSERT INTO List_Wheels VALUES (700, 'FER_FXX_stock');
            INSERT INTO List_Wheels VALUES (701, 'Aftermarket_Front');
            INSERT INTO List_Wheels VALUES (702, 'Aftermarket_Rear');
            """
        )
        connection.commit()
    finally:
        connection.close()


class WheelSpecTests(unittest.TestCase):
    def test_stock_spec_is_read_only_and_has_derived_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            before = _sha256(database)

            spec = FH6WheelSpecResolver(database).resolve(1006)

            after = _sha256(database)

        self.assertEqual(before, after)
        self.assertEqual(spec.mode, "stock")
        self.assertEqual(spec.car_body_id, 343002)
        self.assertEqual(spec.front.tire_width_mm, 255)
        self.assertEqual(spec.front.tire_aspect_ratio, 35)
        self.assertEqual(spec.front.rim_diameter_in, 19)
        self.assertAlmostEqual(spec.front.tire_outer_diameter_mm, 661.1)
        self.assertEqual(spec.front.wheel_style_id, 700)
        self.assertEqual(spec.front.wheel_style_name, "FER_FXX_stock")
        self.assertEqual(spec.rear.wheel_style_id, 700)
        self.assertEqual(spec.tire_compound_id, 1)
        self.assertEqual(spec.tire_model_name, "Street")

    def test_effective_spec_applies_resolved_upgrade_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            selection = WheelUpgradeSelection(
                front_rim_size_id=110,
                rear_rim_size_id=111,
                front_tire_width_id=120,
                rear_tire_width_id=121,
                front_aspect_ratio_id=130,
                rear_aspect_ratio_id=131,
                tire_compound_id=801,
                wheel_style_id=701,
                rear_wheel_style_id=702,
            )

            spec = FH6WheelSpecResolver(database).resolve(1006, selection)

        self.assertEqual(spec.mode, "effective")
        self.assertEqual(spec.front.tire_width_mm, 265)
        self.assertEqual(spec.rear.tire_width_mm, 345)
        self.assertEqual(spec.front.tire_aspect_ratio, 30)
        self.assertEqual(spec.rear.tire_aspect_ratio, 32)
        self.assertEqual(spec.front.rim_diameter_in, 20)
        self.assertEqual(spec.rear.rim_diameter_in, 21)
        self.assertEqual(spec.front.wheel_style_id, 701)
        self.assertEqual(spec.rear.wheel_style_id, 702)
        self.assertEqual(spec.tire_compound_id, 7)
        self.assertEqual(spec.tire_model_name, "Semi_Slick")
        self.assertEqual(
            spec.applied_upgrade_ids["front_rim_size_id"],
            110,
        )

    def test_upgrade_id_from_another_car_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            selection = WheelUpgradeSelection(front_rim_size_id=999)

            with self.assertRaises(WheelSpecError):
                FH6WheelSpecResolver(database).resolve(1006, selection)


if __name__ == "__main__":
    unittest.main()
