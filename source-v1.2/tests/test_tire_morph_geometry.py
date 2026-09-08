from __future__ import annotations

import struct
import tempfile
from pathlib import Path
import unittest
import zipfile

from fh6garage.preview3d.modelbin_morph import BUNDLE_TAG, MESH_TAG, MORPH_BUFFER_TAG
from fh6garage.preview3d.tire_morph_geometry import (
    INDEX_BUFFER_TAG,
    INPUT_LAYOUT_TAG,
    VERTEX_BUFFER_TAG,
    TireMorphGeometryError,
    _glb_bytes,
    bake_modelbin_selector_geometry,
    bake_tire_morph_selectors,
)


def _buffer_payload(raw: bytes, *, stride: int, fmt: int) -> bytes:
    length = len(raw) // stride
    return struct.pack("<iiHBBi", length, len(raw), stride, 1, 0, fmt) + raw


def _layout_payload(position_format: int = 13) -> bytes:
    semantic = b"POSITION"
    data = bytearray()
    data += struct.pack("<H", 1)
    data += struct.pack("<i", len(semantic)) + semantic
    data += struct.pack("<H", 1)
    data += struct.pack("<hhhhiii", 0, 0, 0, 0, position_format, 0, 0)
    data += struct.pack("<i", position_format)
    return bytes(data)


def _mesh_payload(*, vertex_buffer_blob_index: int, position_format: int = 13) -> bytes:
    data = bytearray()
    data += struct.pack("<h", 0)
    data += struct.pack("<h", 0)
    data += struct.pack("<H", 3)
    data += bytes((0, 255))
    data += struct.pack("<H", 1)
    data += bytes((0,))
    data += bytes((0,))
    data += bytes((5,))
    data += bytes((0,))
    data += bytes((0,))
    data += struct.pack("<H", 4)
    data += struct.pack("<iiiiii", 0, 0, 0, -100, 3, 1)
    data += struct.pack("<fI", 0.65, 3)
    data += struct.pack("<i", 0)
    data += struct.pack("<i", 1)
    data += struct.pack(
        "<iIII",
        vertex_buffer_blob_index,
        0,
        8 if position_format == 13 else 12,
        0,
    )
    data += struct.pack("<ii", 0, -1)
    data += struct.pack("<i", 0)
    data += struct.pack("<I", 0)
    data += bytes(80)
    data += struct.pack("<4f", 1.0, 2.0, 3.0, 1.0)
    data += struct.pack("<4f", 10.0, 20.0, 30.0, 0.0)
    return bytes(data)


def _morph_payload() -> bytes:
    records = bytearray()
    selector_deltas = (
        (1.0, 0.0, 0.0),
        (0.0, 2.0, 0.0),
        (0.0, 0.0, 3.0),
        (4.0, 0.0, 0.0),
        (-5.0, 0.0, 0.0),
    )
    for _vertex in range(3):
        for selector, delta in enumerate(selector_deltas):
            records += struct.pack("<eeee", delta[0], delta[1], delta[2], float(selector))
        for selector in range(5):
            records += struct.pack("<eeee", 0.0, 0.0, 0.0, float(selector))
    return _buffer_payload(bytes(records), stride=80, fmt=10)


def _bundle(*, position_format: int = 13) -> bytes:
    index_payload = _buffer_payload(struct.pack("<HHH", 100, 101, 102), stride=2, fmt=57)
    layout_payload = _layout_payload(position_format)
    if position_format == 13:
        vertex_raw = b"".join(
            (
                struct.pack("<hhhh", -32767, 0, 0, 0),
                struct.pack("<hhhh", 0, 32767, 0, 0),
                struct.pack("<hhhh", 0, 0, 32767, 0),
            )
        )
        vertex_stride = 8
    else:
        vertex_raw = bytes(12 * 3)
        vertex_stride = 12
    vertex_payload = _buffer_payload(vertex_raw, stride=vertex_stride, fmt=position_format)
    morph_payload = _morph_payload()
    mesh_payload = _mesh_payload(
        vertex_buffer_blob_index=2,
        position_format=position_format,
    )

    blobs = (
        (INDEX_BUFFER_TAG, 1, 0, index_payload),
        (INPUT_LAYOUT_TAG, 1, 0, layout_payload),
        (VERTEX_BUFFER_TAG, 1, 0, vertex_payload),
        (MORPH_BUFFER_TAG, 1, 0, morph_payload),
        (MESH_TAG, 1, 8, mesh_payload),
    )
    header_size = 0x14
    table_size = len(blobs) * 0x18
    cursor = header_size + table_size
    data = bytearray(cursor + sum(len(payload) for _, _, _, payload in blobs))
    struct.pack_into("<I", data, 0, BUNDLE_TAG)
    data[4] = 1
    data[5] = 1
    struct.pack_into("<I", data, 0x10, len(blobs))
    for index, (tag, major, minor, payload) in enumerate(blobs):
        header = header_size + index * 0x18
        struct.pack_into("<I", data, header, tag)
        data[header + 4] = major
        data[header + 5] = minor
        struct.pack_into("<H", data, header + 6, 0)
        struct.pack_into("<IIII", data, header + 8, 0, cursor, 0, len(payload))
        data[cursor : cursor + len(payload)] = payload
        cursor += len(payload)
    return bytes(data)


class TireMorphGeometryTests(unittest.TestCase):
    def test_selector_bake_uses_signed_base_vertex_and_position_transform(self) -> None:
        source = _bundle()
        before = bytes(source)
        report = bake_modelbin_selector_geometry(
            source,
            entry="tireL_slick.modelbin",
            write_glb=False,
        )
        self.assertEqual(source, before)
        self.assertEqual(report.selected_mesh_count, 1)
        evidence = report.mesh_evidence[0]
        self.assertEqual(evidence.min_vertex_index, 100)
        self.assertEqual(evidence.indexed_vertex_offset, -100)
        self.assertEqual(evidence.resolved_vertex_start, 0)
        self.assertEqual(evidence.position_format, 13)
        self.assertEqual(evidence.position_scale, (1.0, 2.0, 3.0))
        self.assertEqual(evidence.position_translate, (10.0, 20.0, 30.0))

        baseline = report.states["baseline"]["aabb"]
        self.assertEqual(baseline["minimum"], (9.0, 20.0, 30.0))
        self.assertEqual(baseline["maximum"], (10.0, 22.0, 33.0))
        self.assertEqual(
            report.states["selector0"]["span_delta_vs_baseline"],
            [0.0, 0.0, 0.0],
        )
        self.assertEqual(
            report.states["selector0"]["center_delta_vs_baseline"],
            [1.0, 0.0, 0.0],
        )
        self.assertEqual(
            report.states["selector1"]["center_delta_vs_baseline"],
            [0.0, 2.0, 0.0],
        )
        self.assertEqual(
            report.states["selector2"]["center_delta_vs_baseline"],
            [0.0, 0.0, 3.0],
        )
        self.assertEqual(
            report.states["selector3"]["center_delta_vs_baseline"],
            [4.0, 0.0, 0.0],
        )
        self.assertEqual(
            report.states["selector4"]["center_delta_vs_baseline"],
            [-5.0, 0.0, 0.0],
        )

    def test_glb_output_is_valid_glb2_container(self) -> None:
        raw = _glb_bytes(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            (0, 1, 2),
        )
        magic, version, total = struct.unpack_from("<4sII", raw, 0)
        self.assertEqual(magic, b"glTF")
        self.assertEqual(version, 2)
        self.assertEqual(total, len(raw))

    def test_actual_bake_writes_six_glbs_for_one_modelbin(self) -> None:
        source = _bundle()
        with tempfile.TemporaryDirectory() as directory:
            report = bake_modelbin_selector_geometry(
                source,
                entry="tireL_slick.modelbin",
                output_dir=Path(directory),
                write_glb=True,
            )
            self.assertEqual(
                set(report.glb_files),
                {"baseline", "selector0", "selector1", "selector2", "selector3", "selector4"},
            )
            for path in report.glb_files.values():
                self.assertTrue(Path(path).is_file())
                self.assertEqual(Path(path).read_bytes()[:4], b"glTF")

    def test_archive_selector_bake_accepts_no_output_dir_when_glb_writes_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_Vintage.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("tireL_vintage.modelbin", _bundle())
            before = archive.read_bytes()

            report = bake_tire_morph_selectors(
                archive,
                None,
                write_glb=False,
            )

            self.assertTrue(report.archive_read_only_unchanged)
            self.assertEqual(archive.read_bytes(), before)
            self.assertEqual(len(report.modelbins), 1)
            self.assertEqual(report.modelbins[0].glb_files, {})

    def test_unverified_position_format_fails_closed(self) -> None:
        source = _bundle(position_format=10)
        with self.assertRaisesRegex(TireMorphGeometryError, "unsupported POSITION"):
            bake_modelbin_selector_geometry(source, write_glb=False)


if __name__ == "__main__":
    unittest.main()
