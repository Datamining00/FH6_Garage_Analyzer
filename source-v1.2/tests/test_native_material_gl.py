from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.native_dds import DDS_DX10_HEADER_SIZE, parse_native_dds
from fh6garage.preview3d.native_material_gl import (
    NativeMaterialGlError,
    native_gl_texture_spec,
    upload_native_dds_2d,
)


def _write_dds(
    path: Path,
    dxgi: int,
    payload: bytes,
    *,
    width: int = 4,
    height: int = 4,
    mip_levels: int = 1,
) -> None:
    header = bytearray(DDS_DX10_HEADER_SIZE)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 24, 1)
    struct.pack_into("<I", header, 28, mip_levels)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x4)
    header[84:88] = b"DX10"
    struct.pack_into("<I", header, 108, 0x1000)
    struct.pack_into("<IIIII", header, 128, dxgi, 3, 0, 1, 0)
    path.write_bytes(bytes(header) + payload)


class _FakeGl:
    GL_VERSION = 0x1F02
    GL_EXTENSIONS = 0x1F03
    GL_NUM_EXTENSIONS = 0x821D
    GL_TEXTURE_2D = 0x0DE1
    GL_TEXTURE_WRAP_S = 0x2802
    GL_TEXTURE_WRAP_T = 0x2803
    GL_TEXTURE_MIN_FILTER = 0x2801
    GL_TEXTURE_MAG_FILTER = 0x2800
    GL_TEXTURE_BASE_LEVEL = 0x813C
    GL_TEXTURE_MAX_LEVEL = 0x813D
    GL_REPEAT = 0x2901
    GL_LINEAR = 0x2601
    GL_LINEAR_MIPMAP_LINEAR = 0x2703
    GL_NO_ERROR = 0

    def __init__(self, *, version=b"3.3", extensions=()):
        self.version = version
        self.extensions = tuple(item.encode("ascii") for item in extensions)
        self.compressed_calls = []
        self.linear_calls = []
        self.deleted = []
        self.bound = []
        self.tex_parameters = []
        self.next_error = 0

    def glGetString(self, name):
        if name == self.GL_VERSION:
            return self.version
        if name == self.GL_EXTENSIONS:
            return b" ".join(self.extensions)
        return b""

    def glGetIntegerv(self, name):
        return len(self.extensions) if name == self.GL_NUM_EXTENSIONS else 0

    def glGetStringi(self, name, index):
        return self.extensions[index]

    def glGenTextures(self, count):
        return 7

    def glBindTexture(self, target, texture):
        self.bound.append((target, texture))

    def glTexParameteri(self, *args):
        self.tex_parameters.append(args)

    def glCompressedTexImage2D(self, *args):
        self.compressed_calls.append(args)

    def glTexImage2D(self, *args):
        self.linear_calls.append(args)

    def glGetError(self):
        value = self.next_error
        self.next_error = 0
        return value

    def glDeleteTextures(self, ids):
        self.deleted.extend(ids)


class NativeMaterialGlTests(unittest.TestCase):
    def test_dxgi_mapping_is_explicit_and_signed_rgtc_stays_closed(self):
        self.assertEqual(native_gl_texture_spec(99).family, "bc7_srgb")
        self.assertTrue(native_gl_texture_spec(72).compressed)
        self.assertEqual(native_gl_texture_spec(80).internal_format, 0x8DBB)
        self.assertEqual(native_gl_texture_spec(83).internal_format, 0x8DBD)
        self.assertEqual(native_gl_texture_spec(61).internal_format, 0x8229)
        self.assertFalse(native_gl_texture_spec(61).compressed)
        with self.assertRaises(NativeMaterialGlError):
            native_gl_texture_spec(81)  # signed BC4 has no [0,1] roughness contract
        with self.assertRaises(NativeMaterialGlError):
            native_gl_texture_spec(84)  # signed BC5 normal interpretation remains deferred

    def test_bc7_requires_bptc_and_uploads_exact_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bc7.dds"
            payload = bytes(range(16))
            _write_dds(path, 99, payload)
            texture = parse_native_dds(path)

            unsupported = _FakeGl(version=b"3.3", extensions=())
            with self.assertRaisesRegex(NativeMaterialGlError, "bptc"):
                upload_native_dds_2d(unsupported, texture)
            self.assertEqual(unsupported.compressed_calls, [])

            gl = _FakeGl(version=b"3.3", extensions=("GL_ARB_texture_compression_bptc",))
            texture_id = upload_native_dds_2d(gl, texture)
            self.assertEqual(texture_id, 7)
            self.assertEqual(len(gl.compressed_calls), 1)
            call = gl.compressed_calls[0]
            self.assertEqual(call[2], 0x8E8D)
            self.assertEqual(call[6], len(payload))
            self.assertEqual(call[7], payload)
            self.assertEqual(gl.deleted, [])

    def test_bc4_uses_exact_rgtc_payload_and_core_30_support(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "roughness_bc4.dds"
            payload = bytes(range(8))
            _write_dds(path, 80, payload)
            texture = parse_native_dds(path)

            unsupported = _FakeGl(version=b"2.1", extensions=())
            with self.assertRaisesRegex(NativeMaterialGlError, "rgtc"):
                upload_native_dds_2d(unsupported, texture)

            gl = _FakeGl(version=b"3.0", extensions=())
            self.assertEqual(upload_native_dds_2d(gl, texture), 7)
            self.assertEqual(len(gl.compressed_calls), 1)
            call = gl.compressed_calls[0]
            self.assertEqual(call[2], 0x8DBB)
            self.assertEqual(call[6], 8)
            self.assertEqual(call[7], payload)

    def test_bc5_uses_exact_unsigned_two_channel_rgtc_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "normal_bc5.dds"
            payload = bytes(range(16))
            _write_dds(path, 83, payload)
            texture = parse_native_dds(path)
            self.assertEqual(texture.compression_family, "bc5")

            unsupported = _FakeGl(version=b"2.1", extensions=())
            with self.assertRaisesRegex(NativeMaterialGlError, "rgtc"):
                upload_native_dds_2d(unsupported, texture)

            gl = _FakeGl(version=b"3.0", extensions=())
            self.assertEqual(upload_native_dds_2d(gl, texture), 7)
            self.assertEqual(len(gl.compressed_calls), 1)
            call = gl.compressed_calls[0]
            self.assertEqual(call[2], 0x8DBD)  # GL_COMPRESSED_RG_RGTC2
            self.assertEqual(call[6], 16)
            self.assertEqual(call[7], payload)

    def test_r8_upload_uses_red_channel_without_swizzle(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "roughness_r8.dds"
            payload = bytes(range(16))
            _write_dds(path, 61, payload)
            texture = parse_native_dds(path)
            gl = _FakeGl()
            self.assertEqual(upload_native_dds_2d(gl, texture), 7)
            self.assertEqual(len(gl.linear_calls), 1)
            call = gl.linear_calls[0]
            self.assertEqual(call[2], 0x8229)  # GL_R8
            self.assertEqual(call[6], 0x1903)  # GL_RED
            self.assertEqual(call[-1], payload)

    def test_rgba8_upload_uses_exact_linear_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rgba.dds"
            payload = bytes(range(64))
            _write_dds(path, 29, payload)
            texture = parse_native_dds(path)
            gl = _FakeGl()
            self.assertEqual(upload_native_dds_2d(gl, texture), 7)
            self.assertEqual(len(gl.linear_calls), 1)
            call = gl.linear_calls[0]
            self.assertEqual(call[2], 0x8C43)
            self.assertEqual(call[-1], payload)

    def test_partial_mip_chain_sets_explicit_texture_max_level(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "partial_mips.dds"
            payload = bytes((index % 251 for index in range(320)))
            _write_dds(path, 29, payload, width=8, height=8, mip_levels=2)
            texture = parse_native_dds(path)
            gl = _FakeGl()
            self.assertEqual(upload_native_dds_2d(gl, texture), 7)
            self.assertEqual(len(gl.linear_calls), 2)
            self.assertIn((gl.GL_TEXTURE_2D, gl.GL_TEXTURE_BASE_LEVEL, 0), gl.tex_parameters)
            self.assertIn((gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAX_LEVEL, 1), gl.tex_parameters)
            self.assertIn(
                (gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR),
                gl.tex_parameters,
            )

    def test_gl_error_deletes_partial_texture(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bc1.dds"
            _write_dds(path, 71, bytes(range(8)))
            texture = parse_native_dds(path)
            gl = _FakeGl(extensions=("GL_EXT_texture_compression_s3tc",))
            gl.next_error = 0x0500
            with self.assertRaisesRegex(NativeMaterialGlError, "0x0500"):
                upload_native_dds_2d(gl, texture)
            self.assertEqual(gl.deleted, [7])


if __name__ == "__main__":
    unittest.main()