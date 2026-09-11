from __future__ import annotations

import math
import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.native_bc5_normal_analysis import (
    NATIVE_BC5_NORMAL_ANALYSIS_REVISION,
    NativeBc5NormalAnalysisError,
    analyze_bc5_unorm_normal_dds,
)
from fh6garage.preview3d.native_dds import DDS_DX10_HEADER_SIZE


def _write_dds(
    path: Path,
    *,
    dxgi_format: int,
    width: int,
    height: int,
    payload: bytes,
) -> None:
    header = bytearray(DDS_DX10_HEADER_SIZE)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 24, 1)
    struct.pack_into("<I", header, 28, 1)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x4)
    header[84:88] = b"DX10"
    struct.pack_into("<I", header, 108, 0x1000)
    struct.pack_into("<IIIII", header, 128, dxgi_format, 3, 0, 1, 0)
    path.write_bytes(bytes(header) + payload)


def _constant_bc4(value: int) -> bytes:
    return bytes((value, value)) + bytes(6)


def _constant_bc5(red: int, green: int) -> bytes:
    return _constant_bc4(red) + _constant_bc4(green)


class NativeBc5NormalAnalysisTests(unittest.TestCase):
    def test_neutral_unsigned_bc5_evaluates_standard_xy_hypothesis_without_rendering(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "neutral.dds"
            _write_dds(
                path,
                dxgi_format=83,
                width=4,
                height=4,
                payload=_constant_bc5(128, 128),
            )
            report = analyze_bc5_unorm_normal_dds(path)
            self.assertEqual(report.revision, NATIVE_BC5_NORMAL_ANALYSIS_REVISION)
            self.assertEqual(report.status, "bc5_unorm_xy_hypothesis_evaluated")
            self.assertEqual(report.pixel_count, 16)
            self.assertEqual(report.dxgi_format, 83)
            self.assertEqual(report.compression_family, "bc5")
            self.assertFalse(report.rendering_enabled)
            self.assertFalse(report.game_data_modified)
            self.assertTrue(report.hypothesis_only)
            expected_channel = 128.0 / 255.0
            expected_signed = expected_channel * 2.0 - 1.0
            expected_z = math.sqrt(1.0 - 2.0 * expected_signed * expected_signed)
            self.assertAlmostEqual(report.red_unorm_mean, expected_channel, places=7)
            self.assertAlmostEqual(report.green_unorm_mean, expected_channel, places=7)
            self.assertAlmostEqual(report.x_signed_mean, expected_signed, places=7)
            self.assertAlmostEqual(report.y_signed_mean, expected_signed, places=7)
            self.assertAlmostEqual(report.reconstructed_positive_z_mean, expected_z, places=7)
            self.assertEqual(report.xy_outside_unit_disk_count, 0)
            self.assertEqual(report.xy_outside_unit_disk_fraction, 0.0)
            self.assertEqual(
                report.y_orientation_status,
                "undetermined_requires_geometry_or_authoritative_reference",
            )

    def test_outside_unit_disk_is_reported_not_silently_normalized(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "outside.dds"
            _write_dds(
                path,
                dxgi_format=83,
                width=4,
                height=4,
                payload=_constant_bc5(255, 255),
            )
            report = analyze_bc5_unorm_normal_dds(path)
            self.assertEqual(report.xy_outside_unit_disk_count, 16)
            self.assertEqual(report.xy_outside_unit_disk_fraction, 1.0)
            self.assertEqual(report.reconstructed_positive_z_min, 0.0)
            self.assertEqual(report.reconstructed_positive_z_max, 0.0)
            self.assertAlmostEqual(report.xy_length_mean, math.sqrt(2.0), places=7)

    def test_partial_edge_block_crops_to_declared_dimensions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "edge.dds"
            _write_dds(
                path,
                dxgi_format=83,
                width=3,
                height=2,
                payload=_constant_bc5(128, 128),
            )
            report = analyze_bc5_unorm_normal_dds(path)
            self.assertEqual(report.pixel_count, 6)
            self.assertEqual((report.width, report.height), (3, 2))

    def test_non_bc5_unorm_format_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "signed.dds"
            _write_dds(
                path,
                dxgi_format=84,
                width=4,
                height=4,
                payload=_constant_bc5(128, 128),
            )
            with self.assertRaisesRegex(NativeBc5NormalAnalysisError, "DXGI 83"):
                analyze_bc5_unorm_normal_dds(path)


if __name__ == "__main__":
    unittest.main()
