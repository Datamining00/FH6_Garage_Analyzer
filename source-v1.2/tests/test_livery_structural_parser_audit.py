from __future__ import annotations

import struct
import unittest
from pathlib import Path

from fh6garage.livery_preview import _load_backend
from fh6garage.livery_structural_parser_audit import (
    scan_unframed_transform_candidates,
)


def _transform(x: float, y: float, scale: float, rotation: float) -> bytes:
    return struct.pack("<4f", x, y, scale, rotation)


def _counted_group(count: int) -> bytes:
    blocks = (int(count) + 7) // 8
    return b"\x20" + struct.pack("<HH", int(count), blocks) + b"\x00\x00" + bytes(blocks)


def _shape(shape_id: int, x: float = 0.0, y: float = 0.0) -> bytes:
    return (
        b"\x00\x02"
        + struct.pack("<H", int(shape_id))
        + struct.pack("<6f", 0.0, x, y, 1.0, 1.0, 0.0)
        + bytes((0, 0, 255, 255))
    )


class StructuralParserAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decoder, _renderer = _load_backend()

    def test_detects_bare_transform_before_direct_group(self):
        data = _transform(-220.0, 15.0, 1.0, 0.0) + _counted_group(1) + _shape(101)
        candidates = scan_unframed_transform_candidates(self.decoder, data)
        self.assertTrue(candidates)
        item = next(candidate for candidate in candidates if candidate["offset"] == 0)
        self.assertEqual(item["successor"]["kind"], "bare_before_group")
        self.assertAlmostEqual(item["transform"]["x"], -220.0)

    def test_detects_bare_parent_before_extended_child_transform(self):
        marker = b"\x00\x02\x00\x01\x00\x00\x00\x03"
        data = (
            _transform(-373.5, 4.0, 1.0, 0.0)
            + marker
            + _transform(0.0, -2.0, 1.18, 3.6)
            + _counted_group(1)
            + _shape(101)
        )
        candidates = scan_unframed_transform_candidates(self.decoder, data)
        item = next(candidate for candidate in candidates if candidate["offset"] == 0)
        self.assertEqual(item["successor"]["kind"], "bare_before_livery_transform")
        self.assertEqual(item["successor"]["child_marker_hex"], marker.hex())

    def test_does_not_report_framed_livery_transform_as_bare(self):
        framed = b"\x00" + _transform(120.0, 5.0, 1.0, 0.0) + _counted_group(1) + _shape(101)
        candidates = scan_unframed_transform_candidates(self.decoder, framed)
        self.assertFalse(any(candidate["offset"] == 0 for candidate in candidates))

    def test_app_wires_audit_after_bare_parent_fix(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        fix_pos = text.index("apply_livery_bare_parent_transform_fix()")
        audit_pos = text.index("install_livery_structural_parser_audit()")
        ui_pos = text.index("apply_v1_3_ui_patches(MainWindow)")
        self.assertGreater(audit_pos, fix_pos)
        self.assertLess(audit_pos, ui_pos)


if __name__ == "__main__":
    unittest.main()
