from __future__ import annotations

import unittest

from fh6garage.fh6_clivery.records import RawRecord, SourceSpan, Transform
from fh6garage.fh6_clivery.scene import ShapeNode


class LiveryColorOrderTests(unittest.TestCase):
    def _node(self, kind: str, decoded_color: tuple[int, int, int, int]) -> ShapeNode:
        span = SourceSpan(100, 31)
        raw = RawRecord(
            kind,
            span,
            b"\x00" * 27 + bytes((255, 85, 0, 255)),
            "test",
            "02",
        )
        return ShapeNode(
            span,
            raw,
            2217,
            Transform(source_span=span),
            decoded_color,
            "02",
            False,
            "test",
            (2, 0),
        )

    def test_livery_shape_uses_confirmed_raw_rgba_bytes(self) -> None:
        # Shared low-level framing historically interpreted the bytes as BGRA.
        # Pair 4 proves C_livery itself stores these four bytes as RGBA.
        node = self._node("livery_shape_record", (0, 85, 255, 255))
        self.assertEqual(node.color_rgba, (255, 85, 0, 255))

    def test_non_livery_shape_color_is_not_reinterpreted(self) -> None:
        # Keep standalone C_group semantics unchanged until a colored standalone
        # corpus sample independently establishes its byte order.
        node = self._node("shape_record", (0, 85, 255, 255))
        self.assertEqual(node.color_rgba, (0, 85, 255, 255))


if __name__ == "__main__":
    unittest.main()
