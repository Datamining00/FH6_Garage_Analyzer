from __future__ import annotations

import hashlib
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.tuning_wheel_selection import (
    EMPTY_PART_VALUE,
    FH6TuningWheelSelectionResolver,
    TUNING_DATA_SIZE,
    TUNING_PART_COUNT,
    TuningWheelSelectionError,
    decode_part_id,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _encode_part_id(part_id: int) -> int:
    value = int(part_id) & 0xFFFFFFFF
    return ((value & 0xFFFF) << 16) | ((value >> 16) & 0xFFFF)


def _payload(values: dict[int, int]) -> bytes:
    words = [EMPTY_PART_VALUE] * TUNING_PART_COUNT
    for order_id, raw in values.items():
        words[order_id + 3] = int(raw) & 0xFFFFFFFF
    prefix = struct.pack(f"<{TUNING_PART_COUNT}I", *words)
    return prefix + bytes(TUNING_DATA_SIZE - len(prefix))


def _create_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE Data_Car (Id INTEGER PRIMARY KEY, StockWheelID INTEGER);
            CREATE TABLE Data_UpgradePartOrder (Id INTEGER PRIMARY KEY, Name TEXT);
            CREATE TABLE Data_UpgradePart (PartName TEXT PRIMARY KEY, TableName TEXT);
            CREATE TABLE List_UpgradeCarBody (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER, CarBodyID INTEGER
            );
            CREATE TABLE List_UpgradeRimSizeFront (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER, FrontWheelDiameter REAL
            );
            CREATE TABLE List_UpgradeRimSizeRear (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER, RearWheelDiameter REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireWidthFront (
                Id INTEGER PRIMARY KEY, CarBodyID INTEGER, IsStock INTEGER, FrontTireWidth REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireWidthRear (
                Id INTEGER PRIMARY KEY, CarBodyID INTEGER, IsStock INTEGER, RearTireWidth REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireAspectRatioFront (
                Id INTEGER PRIMARY KEY, CarBodyID INTEGER, IsStock INTEGER, FrontTireAspectRatioOffset REAL
            );
            CREATE TABLE List_UpgradeCarBodyTireAspectRatioRear (
                Id INTEGER PRIMARY KEY, CarBodyID INTEGER, IsStock INTEGER, RearTireAspectRatioOffset REAL
            );
            CREATE TABLE List_UpgradeCarBodyTrackSpacingFront (
                Id INTEGER PRIMARY KEY, CarBodyID INTEGER, IsStock INTEGER, Spacing REAL
            );
            CREATE TABLE List_UpgradeCarBodyTrackSpacingRear (
                Id INTEGER PRIMARY KEY, CarBodyID INTEGER, IsStock INTEGER, Spacing REAL
            );
            CREATE TABLE List_UpgradeTireCompound (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER, TireCompoundID INTEGER
            );
            CREATE TABLE List_UpgradeBrakes (
                Id INTEGER PRIMARY KEY, Ordinal INTEGER, IsStock INTEGER, FrontBrakeSizeMM REAL
            );
            CREATE TABLE List_Wheels (ID INTEGER PRIMARY KEY, MediaName TEXT);

            INSERT INTO Data_Car VALUES (1006, 522);
            INSERT INTO Data_Car VALUES (2000, 600);

            INSERT INTO Data_UpgradePartOrder VALUES (0, 'CarBody');
            INSERT INTO Data_UpgradePartOrder VALUES (1, 'RimSizeFront');
            INSERT INTO Data_UpgradePartOrder VALUES (2, 'RimSizeRear');
            INSERT INTO Data_UpgradePartOrder VALUES (3, 'TireWidthFront');
            INSERT INTO Data_UpgradePartOrder VALUES (4, 'TireWidthRear');
            INSERT INTO Data_UpgradePartOrder VALUES (5, 'FrontAspectRatio');
            INSERT INTO Data_UpgradePartOrder VALUES (6, 'RearAspectRatio');
            INSERT INTO Data_UpgradePartOrder VALUES (7, 'TrackSpacingFront');
            INSERT INTO Data_UpgradePartOrder VALUES (8, 'TrackSpacingRear');
            INSERT INTO Data_UpgradePartOrder VALUES (9, 'TireCompound');
            INSERT INTO Data_UpgradePartOrder VALUES (10, 'Brakes');
            INSERT INTO Data_UpgradePartOrder VALUES (11, 'WheelStyle');
            INSERT INTO Data_UpgradePartOrder VALUES (12, 'WheelStyleRear');

            INSERT INTO Data_UpgradePart VALUES ('CarBody', 'List_UpgradeCarBody');
            INSERT INTO Data_UpgradePart VALUES ('RimSizeFront', 'List_UpgradeRimSizeFront');
            INSERT INTO Data_UpgradePart VALUES ('RimSizeRear', 'List_UpgradeRimSizeRear');
            INSERT INTO Data_UpgradePart VALUES ('TireWidthFront', 'List_UpgradeCarBodyTireWidthFront');
            INSERT INTO Data_UpgradePart VALUES ('TireWidthRear', 'List_UpgradeCarBodyTireWidthRear');
            INSERT INTO Data_UpgradePart VALUES ('FrontAspectRatio', 'List_UpgradeCarBodyTireAspectRatioFront');
            INSERT INTO Data_UpgradePart VALUES ('RearAspectRatio', 'List_UpgradeCarBodyTireAspectRatioRear');
            INSERT INTO Data_UpgradePart VALUES ('TrackSpacingFront', 'List_UpgradeCarBodyTrackSpacingFront');
            INSERT INTO Data_UpgradePart VALUES ('TrackSpacingRear', 'List_UpgradeCarBodyTrackSpacingRear');
            INSERT INTO Data_UpgradePart VALUES ('TireCompound', 'List_UpgradeTireCompound');
            INSERT INTO Data_UpgradePart VALUES ('Brakes', 'List_UpgradeBrakes');
            INSERT INTO Data_UpgradePart VALUES ('WheelStyle', 'List_Wheels');
            INSERT INTO Data_UpgradePart VALUES ('WheelStyleRear', 'List_Wheels');

            INSERT INTO List_UpgradeCarBody VALUES (1006000,1006,1,1006000);
            INSERT INTO List_UpgradeRimSizeFront VALUES (1006000,1006,1,19);
            INSERT INTO List_UpgradeRimSizeFront VALUES (1006001,1006,0,20);
            INSERT INTO List_UpgradeRimSizeRear VALUES (1006000,1006,1,19);
            INSERT INTO List_UpgradeRimSizeRear VALUES (1006002,1006,0,21);
            INSERT INTO List_UpgradeCarBodyTireWidthFront VALUES (1006000,1006000,1,245);
            INSERT INTO List_UpgradeCarBodyTireWidthFront VALUES (1006003,1006000,0,315);
            INSERT INTO List_UpgradeCarBodyTireWidthRear VALUES (1006000,1006000,1,345);
            INSERT INTO List_UpgradeCarBodyTireWidthRear VALUES (1006002,1006000,0,365);
            INSERT INTO List_UpgradeCarBodyTireAspectRatioFront VALUES (1006000,1006000,1,0);
            INSERT INTO List_UpgradeCarBodyTireAspectRatioRear VALUES (1006000,1006000,1,0);
            INSERT INTO List_UpgradeCarBodyTrackSpacingFront VALUES (1006000,1006000,1,0);
            INSERT INTO List_UpgradeCarBodyTrackSpacingFront VALUES (1006003,1006000,0,0.09);
            INSERT INTO List_UpgradeCarBodyTrackSpacingRear VALUES (1006000,1006000,1,0);
            INSERT INTO List_UpgradeCarBodyTrackSpacingRear VALUES (1006003,1006000,0,0.08);
            INSERT INTO List_UpgradeTireCompound VALUES (1006000,1006,1,13);
            INSERT INTO List_UpgradeTireCompound VALUES (1006007,1006,0,7);
            INSERT INTO List_UpgradeBrakes VALUES (1006000,1006,1,398);
            INSERT INTO List_UpgradeBrakes VALUES (1006001,1006,0,410);
            INSERT INTO List_Wheels VALUES (522,'FER_FXX_05');
            INSERT INTO List_Wheels VALUES (701,'AftermarketFront');
            INSERT INTO List_Wheels VALUES (702,'AftermarketRear');

            INSERT INTO List_UpgradeRimSizeFront VALUES (2000001,2000,0,24);
            """
        )
        connection.commit()
    finally:
        connection.close()


class TuningWheelSelectionTests(unittest.TestCase):
    def test_decode_part_id_swaps_16_bit_halves(self):
        self.assertEqual(decode_part_id(0x56781234), 0x12345678)
        self.assertEqual(decode_part_id(EMPTY_PART_VALUE), -1)

    def test_stock_payload_resolves_but_produces_empty_effective_selections(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            before = _sha256(database)
            data = _payload(
                {
                    0: _encode_part_id(1006000),
                    1: _encode_part_id(1006000),
                    2: _encode_part_id(1006000),
                    3: _encode_part_id(1006000),
                    4: _encode_part_id(1006000),
                    5: _encode_part_id(1006000),
                    6: _encode_part_id(1006000),
                    7: _encode_part_id(1006000),
                    8: _encode_part_id(1006000),
                    9: _encode_part_id(1006000),
                    10: _encode_part_id(1006000),
                    11: 522 << 16,
                    12: 522 << 16,
                }
            )
            result = FH6TuningWheelSelectionResolver(database).resolve_bytes(1006, data)
            after = _sha256(database)

        self.assertEqual(before, after)
        self.assertTrue(result.wheel.is_stock())
        self.assertTrue(result.placement.is_stock())
        self.assertEqual(result.unresolved_slots, ())
        self.assertEqual(result.resolved_parts["WheelStyle"].resolved_row_id, 522)
        self.assertEqual(result.resolved_parts["RimSizeFront"].payload_index, 4)

    def test_modified_payload_maps_to_w1_and_w12_selection_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            data = _payload(
                {
                    0: _encode_part_id(1006000),
                    1: _encode_part_id(1006001),
                    2: _encode_part_id(1006002),
                    3: _encode_part_id(1006003),
                    4: _encode_part_id(1006002),
                    5: _encode_part_id(1006000),
                    6: _encode_part_id(1006000),
                    7: _encode_part_id(1006003),
                    8: _encode_part_id(1006003),
                    9: _encode_part_id(1006007),
                    10: _encode_part_id(1006001),
                    11: 701 << 16,
                    12: 702 << 16,
                }
            )
            result = FH6TuningWheelSelectionResolver(database).resolve_bytes(1006, data)

        self.assertEqual(result.wheel.front_rim_size_id, 1006001)
        self.assertEqual(result.wheel.rear_rim_size_id, 1006002)
        self.assertEqual(result.wheel.front_tire_width_id, 1006003)
        self.assertEqual(result.wheel.rear_tire_width_id, 1006002)
        self.assertIsNone(result.wheel.front_aspect_ratio_id)
        self.assertIsNone(result.wheel.rear_aspect_ratio_id)
        self.assertEqual(result.wheel.tire_compound_id, 1006007)
        self.assertEqual(result.wheel.wheel_style_id, 701)
        self.assertEqual(result.wheel.rear_wheel_style_id, 702)
        self.assertEqual(result.placement.front_track_spacing_id, 1006003)
        self.assertEqual(result.placement.rear_track_spacing_id, 1006003)
        self.assertEqual(result.placement.tire_compound_id, 1006007)
        self.assertEqual(result.placement.brakes_id, 1006001)
        self.assertIsNone(result.placement.car_body_upgrade_id)
        self.assertEqual(result.unresolved_slots, ())

    def test_wrong_car_upgrade_is_not_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            data = _payload({1: _encode_part_id(2000001)})
            result = FH6TuningWheelSelectionResolver(database).resolve_bytes(1006, data)

        self.assertIsNone(result.wheel.front_rim_size_id)
        self.assertIn("RimSizeFront", result.unresolved_slots)

    def test_payload_size_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fh6.sqlite"
            _create_fixture(database)
            with self.assertRaises(TuningWheelSelectionError):
                FH6TuningWheelSelectionResolver(database).resolve_bytes(1006, bytes(597))


if __name__ == "__main__":
    unittest.main()
