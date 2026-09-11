from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.wheel_placement import (
    FH6WheelPlacementResolver,
    WheelPlacementSelection,
)
from fh6garage.preview3d.wheel_spec import WheelSpecError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE Data_Car (Id INTEGER PRIMARY KEY);
            CREATE TABLE List_UpgradeCarBody (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER, CarBodyID INTEGER
            );
            CREATE TABLE Data_CarBody (
                Id INTEGER PRIMARY KEY,
                ModelWheelbase REAL,
                ModelFrontTrackOuter REAL,
                ModelRearTrackOuter REAL,
                ModelFrontStockRideHeight REAL,
                ModelRearStockRideHeight REAL,
                BottomCenterWheelbasePosx REAL,
                BottomCenterWheelbasePosy REAL,
                BottomCenterWheelbasePosZ REAL
            );
            CREATE TABLE List_UpgradeCarBodyTrackSpacingFront (
                Id INTEGER PRIMARY KEY, CarBodyId INTEGER, IsStock INTEGER, Spacing REAL
            );
            CREATE TABLE List_UpgradeCarBodyTrackSpacingRear (
                Id INTEGER PRIMARY KEY, CarBodyId INTEGER, IsStock INTEGER, Spacing REAL
            );
            CREATE TABLE List_UpgradeTireCompound (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER,
                FrontTrackSpacerOffset REAL, RearTrackSpacerOffset REAL
            );
            CREATE TABLE List_UpgradeBrakes (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER,
                FrontBrakeSizeMM REAL, FrontBrakeRotorThicknessMM REAL,
                FrontBrakeDrumDepthMM REAL, FrontBrakeNonSpinningMass REAL,
                FrontBrakeTypeID INTEGER, FrontCaliperPistons INTEGER,
                RearBrakeSizeMM REAL, RearBrakeRotorThicknessMM REAL,
                RearBrakeDrumDepthMM REAL, RearBrakeNonSpinningMass REAL,
                RearBrakeTypeID INTEGER, RearCaliperPistons INTEGER
            );

            INSERT INTO Data_Car VALUES (1006);
            INSERT INTO Data_Car VALUES (2000);
            INSERT INTO List_UpgradeCarBody VALUES (1006000,1006,1,1006000);
            INSERT INTO List_UpgradeCarBody VALUES (2000000,2000,1,2000000);
            INSERT INTO Data_CarBody VALUES (
                1006000,2.639188,1.9,1.95,0.13,0.14,0.0,0.0,-0.005
            );
            INSERT INTO Data_CarBody VALUES (
                2000000,2.8,1.7,1.72,0.12,0.12,0.0,0.0,0.0
            );
            INSERT INTO List_UpgradeCarBodyTrackSpacingFront VALUES (1006000,1006000,1,0.0);
            INSERT INTO List_UpgradeCarBodyTrackSpacingFront VALUES (1006003,1006000,0,0.09);
            INSERT INTO List_UpgradeCarBodyTrackSpacingFront VALUES (2000001,2000000,0,0.10);
            INSERT INTO List_UpgradeCarBodyTrackSpacingRear VALUES (1006000,1006000,1,0.0);
            INSERT INTO List_UpgradeCarBodyTrackSpacingRear VALUES (1006003,1006000,0,0.08);
            INSERT INTO List_UpgradeTireCompound VALUES (1006000,1006,1,0.0,0.0);
            INSERT INTO List_UpgradeTireCompound VALUES (1006007,1006,0,-0.055,-0.055);
            INSERT INTO List_UpgradeBrakes VALUES (
                1006000,1006,1,398,35,65,4,5,6,381,35,65,4,5,4
            );
            INSERT INTO List_UpgradeBrakes VALUES (
                1006001,1006,0,410,36,66,4.2,5,6,390,36,66,4.2,5,4
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


class WheelPlacementTests(unittest.TestCase):
    def test_stock_placement_is_read_only_and_uses_real_geometry_relationships(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            before = _sha256(database)
            spec = FH6WheelPlacementResolver(database).resolve(1006)
            after = _sha256(database)

        self.assertEqual(before, after)
        self.assertEqual(spec.mode, "stock")
        self.assertEqual(spec.car_body_id, 1006000)
        self.assertAlmostEqual(spec.model_wheelbase_m, 2.639188)
        self.assertAlmostEqual(spec.front.effective_track_outer_m, 1.9)
        self.assertAlmostEqual(spec.rear.effective_track_outer_m, 1.95)
        self.assertAlmostEqual(spec.front.half_track_m, 0.95)
        self.assertAlmostEqual(spec.front_axle_z_m, -0.005 + 2.639188 / 2)
        self.assertAlmostEqual(spec.rear_axle_z_m, -0.005 - 2.639188 / 2)
        self.assertEqual(spec.front_brake.size_mm, 398)
        self.assertEqual(spec.rear_brake.size_mm, 381)
        self.assertEqual(spec.front_brake.caliper_pistons, 6)
        self.assertEqual(spec.rear_brake.caliper_pistons, 4)

    def test_effective_track_spacing_and_tire_offset_are_kept_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            selection = WheelPlacementSelection(
                front_track_spacing_id=1006003,
                rear_track_spacing_id=1006003,
                tire_compound_id=1006007,
                brakes_id=1006001,
            )
            spec = FH6WheelPlacementResolver(database).resolve(1006, selection)

        self.assertEqual(spec.mode, "effective")
        self.assertAlmostEqual(spec.front.track_spacing_m, 0.09)
        self.assertAlmostEqual(spec.rear.track_spacing_m, 0.08)
        self.assertAlmostEqual(spec.front.effective_track_outer_m, 1.99)
        self.assertAlmostEqual(spec.rear.effective_track_outer_m, 2.03)
        self.assertAlmostEqual(spec.front.tire_compound_spacer_offset_m, -0.055)
        self.assertAlmostEqual(spec.rear.tire_compound_spacer_offset_m, -0.055)
        self.assertEqual(spec.front_brake.size_mm, 410)
        self.assertEqual(spec.rear_brake.size_mm, 390)

    def test_track_spacing_from_another_car_body_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            selection = WheelPlacementSelection(front_track_spacing_id=2000001)
            with self.assertRaises(WheelSpecError):
                FH6WheelPlacementResolver(database).resolve(1006, selection)


if __name__ == "__main__":
    unittest.main()
