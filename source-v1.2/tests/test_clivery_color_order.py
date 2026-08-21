from __future__ import annotations

import unittest

from fh6garage.fh6_clivery.records import RawRecord, SourceSpan, Transform
from fh6garage.fh6_clivery.scene import ShapeNode


class LiveryColorOrderTests(unittest.TestCase):
    def _node(
        self,
        kind: str,
        decoded_color: tuple[int, int, int, int],
        stored_color: tuple[int, int, int, int],
    ) -> ShapeNode:
        span = SourceSpan(100, 31)
        raw = RawRecord(
            kind,
            span,
            b"\x00" * 27 + bytes(stored_color),
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

    def test_livery_shape_keeps_shared_bgra_to_rgba_decode(self) -> None:
        # Pair 5 screenshot proves stored [B,G,R,A] = [0,0,255,255]
        # renders red. ShapeNode must therefore preserve the shared parser's
        # semantic RGBA result instead of reinterpreting raw livery bytes.
        node = self._node(
            "livery_shape_record",
            (255, 0, 0, 255),
            (0, 0, 255, 255),
        )
        self.assertEqual(node.color_rgba, (255, 0, 0, 255))

    def test_standalone_shape_semantics_remain_unchanged(self) -> None:
        node = self._node(
            "shape_record",
            (255, 0, 0, 255),
            (0, 0, 255, 255),
        )
        self.assertEqual(node.color_rgba, (255, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
