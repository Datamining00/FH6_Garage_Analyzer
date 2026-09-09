from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.native_dds import (
    DDS_DX10_HEADER_SIZE,
    NativeDdsError,
    native_dds_mip_bytes,
    parse_native_dds,
)


def _write_dds(
    path: Path,
    *,
    width: int,
    height: int,
    mip_levels: int,
    dxgi_format: int,
    payload: bytes,
    depth: int = 1,
    resource_dimension: int = 3,
    misc_flag: int = 0,
    array_size: int = 1,
) -> None:
    header = bytearray(DDS_DX10_HEADER_SIZE)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 24, depth)
    struct.pack_into("<I", header, 28, mip_levels)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x4)
    header[84:88] = b"DX10"
    struct.pack_into("<I", header, 108, 0x1000)
    struct.pack_into(
        "<IIIII",
        header,
        128,
        dxgi_format,
        resource_dimension,
        misc_flag,
        array_size,
        0,
    )
    path.write_bytes(bytes(header) + payload)


class NativeDdsTests(unittest.TestCase):
    def test_parses_bc7_srgb_mip_layout_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paint.dds"
            mip0 = bytes(range(64))
            mip1 = bytes(range(16))
            mip2 = bytes(range(16, 32))
            _write_dds(
                path,
                width=8,
                height=8,
                mip_levels=3,
                dxgi_format=99,
                payload=mip0 + mip1 + mip2,
            )
            texture = parse_native_dds(path)
            self.assertTrue(texture.is_simple_2d)
            self.assertTrue(texture.is_srgb)
            self.assertEqual(texture.compression_family, "bc7")
            self.assertEqual(texture.block_bytes, 16)
            self.assertIsNone(texture.bits_per_pixel)
            self.assertEqual(texture.width, 8)
            self.assertEqual(texture.height, 8)
            self.assertEqual(texture.mip_levels, 3)
            self.assertEqual(
                [(m.width, m.height, m.offset, m.size) for m in texture.mips],
                [
                    (8, 8, 148, 64),
                    (4, 4, 212, 16),
                    (2, 2, 228, 16),
                ],
            )
            self.assertEqual(native_dds_mip_bytes(texture, 0), mip0)
            self.assertEqual(native_dds_mip_bytes(texture, 1), mip1)
            self.assertEqual(native_dds_mip_bytes(texture, 2), mip2)

    def test_parses_rgba8_linear_mips(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rgba.dds"
            mip0 = bytes(4 * 2 * 4)
            mip1 = bytes(2 * 1 * 4)
            _write_dds(
                path,
                width=4,
                height=2,
                mip_levels=2,
                dxgi_format=28,
                payload=mip0 + mip1,
            )
            texture = parse_native_dds(path)
            self.assertFalse(texture.is_srgb)
            self.assertEqual(texture.compression_family, "rgba8")
            self.assertEqual(texture.bits_per_pixel, 32)
            self.assertIsNone(texture.block_bytes)
            self.assertEqual([m.size for m in texture.mips], [32, 8])

    def test_rejects_unknown_dxgi_instead_of_assuming_32bpp(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unknown.dds"
            _write_dds(
                path,
                width=4,
                height=4,
                mip_levels=1,
                dxgi_format=12345,
                payload=bytes(64),
            )
            with self.assertRaisesRegex(NativeDdsError, "Unsupported native DDS DXGI format"):
                parse_native_dds(path)

    def test_rejects_truncated_and_trailing_payloads(self):
        with tempfile.TemporaryDirectory() as temp:
            truncated = Path(temp) / "truncated.dds"
            _write_dds(
                truncated,
                width=4,
                height=4,
                mip_levels=1,
                dxgi_format=99,
                payload=bytes(15),
            )
            with self.assertRaisesRegex(NativeDdsError, "truncated"):
                parse_native_dds(truncated)

            trailing = Path(temp) / "trailing.dds"
            _write_dds(
                trailing,
                width=4,
                height=4,
                mip_levels=1,
                dxgi_format=99,
                payload=bytes(17),
            )
            with self.assertRaisesRegex(NativeDdsError, "unexpected trailing"):
                parse_native_dds(trailing)

    def test_rejects_3d_texture_layout_for_current_viewer(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "volume.dds"
            _write_dds(
                path,
                width=4,
                height=4,
                depth=2,
                resource_dimension=4,
                mip_levels=1,
                dxgi_format=99,
                payload=bytes(32),
            )
            with self.assertRaisesRegex(NativeDdsError, "3D texture"):
                parse_native_dds(path)

    def test_mip_reader_rechecks_file_length(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paint.dds"
            _write_dds(
                path,
                width=4,
                height=4,
                mip_levels=1,
                dxgi_format=99,
                payload=bytes(16),
            )
            texture = parse_native_dds(path)
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(NativeDdsError, "became truncated"):
                native_dds_mip_bytes(texture, 0)


if __name__ == "__main__":
    unittest.main()
