from __future__ import annotations

import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from fh6garage.preview3d.manufacturer_colors import (
    BUNDLE_TAG,
    MANUFACTURER_COLORS_BLOB_TAG,
    ManufacturerColorsError,
    diagnose_manufacturer_colors_archive,
    parse_manufacturer_colors_bundle,
    resolve_manufacturer_group_linear_paint,
    resolve_manufacturer_selector,
)


def _write_7bit(value: int) -> bytes:
    if value < 0 or value > 0x7FFFFFFF:
        raise ValueError(value)
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return _write_7bit(len(raw)) + raw


def _color(r: float, g: float, b: float) -> bytes:
    return struct.pack("<fff", r, g, b)


def _entry(material_names: list[str], preview=(0.1, 0.2, 0.3), path="materials/carpaint.swatchbin") -> bytes:
    result = bytearray(struct.pack("<I", len(material_names)))
    for name in material_names:
        result += _string(name)
    result += _color(*preview)
    result += _string(path)
    return bytes(result)


def _trailer(
    primary=(0.4, 0.5, 0.6),
    secondary=(0.7, 0.8, 0.9),
    *,
    primary_present=1,
    secondary_present=1,
) -> bytes:
    return bytes([primary_present]) + _color(*primary) + bytes([0, secondary_present]) + _color(*secondary)


def _manufacturer_payload(*, long_name: bool = False, trailing: bytes = b"\xaa\xbb") -> bytes:
    names = ["carpaint"]
    if long_name:
        names.append("m" * 130)
    result = bytearray([2])
    result += bytes([1])
    result += _entry(names)
    result += _trailer()
    result += bytes([0])
    result += _trailer(primary=(0.11, 0.22, 0.33), secondary=(0.44, 0.55, 0.66), secondary_present=0)
    result += trailing
    return bytes(result)


def _bundle(blobs: list[tuple[int, int, int, bytes]]) -> bytes:
    header_size = 20 + 24 * len(blobs)
    offsets: list[int] = []
    cursor = header_size
    for _tag, _major, _minor, payload in blobs:
        offsets.append(cursor)
        cursor += len(payload)
    total_size = cursor
    result = bytearray(struct.pack("<IBBhIII", BUNDLE_TAG, 1, 1, 0, header_size, total_size, len(blobs)))
    for (tag, major, minor, payload), offset in zip(blobs, offsets):
        result += struct.pack(
            "<IBBHIIII",
            tag,
            major,
            minor,
            0,
            0,
            offset,
            len(payload),
            len(payload),
        )
    for _tag, _major, _minor, payload in blobs:
        result += payload
    return bytes(result)


def _manufacturer_bundle(*, long_name: bool = False, trailing: bytes = b"\xaa\xbb") -> bytes:
    return _bundle([(MANUFACTURER_COLORS_BLOB_TAG, 2, 0, _manufacturer_payload(long_name=long_name, trailing=trailing))])


class ManufacturerColorsTests(unittest.TestCase):
    def test_parses_fh6_v2_groups_entries_trailers_and_multibyte_7bit_strings(self):
        report = parse_manufacturer_colors_bundle(_manufacturer_bundle(long_name=True))
        self.assertEqual(report["status"], "manufacturer_colors_parsed")
        self.assertEqual(report["source_contract"], "forzatechstudio_4f373c5_manufacturercolorsblob_v2")
        self.assertEqual(report["bundle_version"], [1, 1])
        self.assertEqual(report["blob_version"], [2, 0])
        self.assertEqual(report["group_count"], 2)
        first = report["groups"][0]
        self.assertEqual(first["entry_count"], 1)
        self.assertEqual(first["entries"][0]["material_names"][0], "carpaint")
        self.assertEqual(first["entries"][0]["material_names"][1], "m" * 130)
        self.assertEqual(first["entries"][0]["path"], "materials/carpaint.swatchbin")
        self.assertTrue(first["primary_group_preview_present"])
        self.assertTrue(first["secondary_group_preview_present"])
        self.assertEqual(report["groups"][1]["entry_count"], 0)
        self.assertFalse(report["groups"][1]["secondary_group_preview_present"])
        self.assertEqual(report["blob_trailing"]["size"], 2)
        self.assertEqual(report["blob_trailing"]["hex"], "aabb")
        self.assertFalse(report["rendering_applied"])
        self.assertFalse(report["game_data_modified"])

    def test_selector_resolves_group_index_but_does_not_choose_material_entry(self):
        report = parse_manufacturer_colors_bundle(_manufacturer_bundle())
        resolved = resolve_manufacturer_selector(report, 0)
        self.assertEqual(resolved["status"], "manufacturer_group_resolved")
        self.assertEqual(resolved["group"]["index"], 0)
        empty = resolve_manufacturer_selector(report, 1)
        self.assertEqual(empty["status"], "manufacturer_selector_empty_group")
        self.assertEqual(resolve_manufacturer_selector(report, 2)["status"], "manufacturer_selector_out_of_range")
        self.assertEqual(resolve_manufacturer_selector(report, 0xFFFFFFFF)["status"], "custom_color_selector")

    def test_p3b_resolves_group_trailer_primary_as_linear_and_preserves_secondary_diagnostic(self):
        report = parse_manufacturer_colors_bundle(_manufacturer_bundle())
        resolved = resolve_manufacturer_group_linear_paint(report, 0)
        self.assertEqual(resolved["status"], "manufacturer_primary_linear_resolved")
        self.assertEqual(resolved["group_index"], 0)
        self.assertEqual(resolved["entry_count"], 1)
        for actual, expected in zip(resolved["primary_linear_rgb"], [0.4, 0.5, 0.6]):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertTrue(resolved["secondary_enabled"])
        for actual, expected in zip(resolved["secondary_linear_rgb"], [0.7, 0.8, 0.9]):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertEqual(resolved["secondary_status"], "manufacturer_secondary_trailer_preserved_deferred")

    def test_p3b_primary_resolution_fails_closed_if_trailer_marks_primary_absent(self):
        report = parse_manufacturer_colors_bundle(_manufacturer_bundle())
        report["groups"][0]["primary_group_preview_present"] = False
        resolved = resolve_manufacturer_group_linear_paint(report, 0)
        self.assertEqual(resolved["status"], "manufacturer_primary_trailer_absent")
        self.assertIsNone(resolved["primary_linear_rgb"])

    def test_p3b_group_linear_color_uses_same_unit_clamp_as_reference_display_conversion(self):
        report = parse_manufacturer_colors_bundle(_manufacturer_bundle())
        report["groups"][0]["primary_group_preview_color"] = [-0.25, 0.5, 1.25]
        resolved = resolve_manufacturer_group_linear_paint(report, 0)
        self.assertEqual(resolved["status"], "manufacturer_primary_linear_resolved")
        self.assertEqual(resolved["primary_linear_rgb"], [0.0, 0.5, 1.0])

    def test_archive_lookup_is_case_insensitive_and_basename_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "car.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Data/Vehicle/MANUFACTURERCOLORS.BIN", _manufacturer_bundle())
                bundle.writestr("Data/Vehicle/not_manufacturercolors.bin.txt", b"ignored")
            report = diagnose_manufacturer_colors_archive(archive)
            self.assertEqual(report["status"], "manufacturer_colors_parsed")
            self.assertEqual(report["archive_entry"], "Data/Vehicle/MANUFACTURERCOLORS.BIN")
            self.assertEqual(report["group_count"], 2)

    def test_missing_archive_member_is_normal_nonrendering_state(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "car.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("CarBody/body.modelbin", b"model")
            report = diagnose_manufacturer_colors_archive(archive)
            self.assertEqual(report["status"], "manufacturer_colors_not_present")
            self.assertEqual(report["groups"], [])
            self.assertFalse(report["rendering_applied"])

    def test_duplicate_archive_members_fail_closed_as_ambiguous(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "car.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("A/ManufacturerColors.bin", _manufacturer_bundle())
                bundle.writestr("B/manufacturercolors.bin", _manufacturer_bundle())
            report = diagnose_manufacturer_colors_archive(archive)
            self.assertEqual(report["status"], "manufacturer_colors_archive_member_ambiguous")
            self.assertEqual(len(report["candidate_entries"]), 2)
            self.assertFalse(report["rendering_applied"])

    def test_multiple_manufacturer_blobs_are_rejected(self):
        payload = _manufacturer_payload(trailing=b"")
        raw = _bundle(
            [
                (MANUFACTURER_COLORS_BLOB_TAG, 2, 0, payload),
                (MANUFACTURER_COLORS_BLOB_TAG, 2, 0, payload),
            ]
        )
        with self.assertRaisesRegex(ManufacturerColorsError, "exact palette source is ambiguous"):
            parse_manufacturer_colors_bundle(raw)

    def test_truncated_fh6_group_trailer_is_rejected(self):
        payload = bytes([1, 0]) + b"\x01\x00"
        raw = _bundle([(MANUFACTURER_COLORS_BLOB_TAG, 2, 0, payload)])
        with self.assertRaisesRegex(ManufacturerColorsError, "27-byte FH6 preview trailer"):
            parse_manufacturer_colors_bundle(raw)


if __name__ == "__main__":
    unittest.main()
