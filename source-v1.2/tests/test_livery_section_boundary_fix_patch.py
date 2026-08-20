from __future__ import annotations

import struct
import unittest

from fh6garage.livery_preview import _load_backend
from fh6garage.livery_section_boundary_fix_patch import (
    _build_livery_sections_boundary_safe,
    _direct_placement_at,
)


def _shape(shape_id: int, *, x: float = 0.0, color=(0, 0, 0, 255), lead: bytes = b"\x00\x02") -> bytes:
    if lead not in (b"\x00\x02", b"\x01\x02"):
        raise ValueError("unsupported test lead")
    r, g, b, a = color
    return b"".join(
        (
            lead,
            struct.pack("<H", int(shape_id)),
            struct.pack("<6f", 0.0, float(x), 0.0, 1.0, 1.0, 0.0),
            bytes((b, g, r, a)),
        )
    )


class LiverySectionBoundaryFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decoder, _renderer = _load_backend()

    def test_exact_boundary_direct_shape_is_preserved(self):
        first = _shape(101, x=-12.0)
        second = _shape(104, x=12.0)
        # Two populated sections followed by the standard second-section remnant
        # and nine empty slots. The crucial property is that section 2 begins
        # immediately at offset 32 rather than after an 18-byte remnant.
        body = first + second + (b"\x00" * 18) + (b"\x00" * (9 * 23))
        counts = [1, 1] + [0] * 9

        self.assertTrue(_direct_placement_at(self.decoder, body, 32, len(body)))
        layers, warnings = _build_livery_sections_boundary_safe(self.decoder, body, counts)

        self.assertEqual(len(layers), 2)
        self.assertEqual([layer.get("section") for layer in layers], ["Front", "Back"])
        self.assertEqual([layer.get("source_offset") for layer in layers], [0, 32])
        self.assertTrue(any("remnant skip suppressed" in warning for warning in warnings))

    def test_zero_remnant_is_not_mistaken_for_direct_placement(self):
        body = b"\x00" * 64
        self.assertFalse(_direct_placement_at(self.decoder, body, 0, len(body)))

    def test_01_02_shape_is_valid_next_section_start(self):
        body = _shape(101, lead=b"\x01\x02") + (b"\x00" * 32)
        self.assertTrue(_direct_placement_at(self.decoder, body, 0, len(body)))


if __name__ == "__main__":
    unittest.main()
