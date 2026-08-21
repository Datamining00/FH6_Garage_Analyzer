from __future__ import annotations

import unittest

from fh6garage.fh6_clivery.flatten import FlattenError, _resolve_masks
from fh6garage.fh6_clivery.records import RawRecord, SourceSpan, Transform
from fh6garage.fh6_clivery.scene import GroupNode, ShapeNode


class TerminalSectionMaskTests(unittest.TestCase):
    def _shape(self, offset: int, color: tuple[int, int, int, int]) -> ShapeNode:
        span = SourceSpan(offset, 31)
        raw = RawRecord("shape", span, b"\x00" * 31, "test", "02")
        return ShapeNode(
            span,
            raw,
            2217,
            Transform(source_span=span),
            color,
            "02",
            False,
            "test",
            (2, 0),
        )

    def _group(self, children: list[object]) -> GroupNode:
        span = SourceSpan(0, 7)
        raw = RawRecord("root", span, b"\x00" * 7, "test", None)
        return GroupNode(
            span,
            span,
            raw,
            "",
            len(children),
            b"\x00",
            Transform(),
            False,
            "NO_CONFIRMED_MASK_ANCESTRY",
            (2,),
            list(children),
            [],
            True,
        )

    def test_terminal_state_one_masks_terminal_direct_achromatic_shape(self) -> None:
        shape = self._shape(287, (255, 255, 255, 255))
        masks = _resolve_masks(self._group([shape]), terminal_state=1)
        self.assertEqual(masks[id(shape)], (True, ("section_terminal_state_01",)))

    def test_terminal_state_zero_does_not_mask_terminal_shape(self) -> None:
        shape = self._shape(287, (255, 255, 255, 255))
        masks = _resolve_masks(self._group([shape]), terminal_state=0)
        self.assertEqual(masks[id(shape)], (False, ("NO_EFFECTIVE_MASK",)))

    def test_nonzero_terminal_state_after_group_fails_closed(self) -> None:
        child_shape = self._shape(300, (255, 255, 255, 255))
        child_group = self._group([child_shape])
        with self.assertRaises(FlattenError):
            _resolve_masks(self._group([child_group]), terminal_state=1)

    def test_terminal_state_one_masks_terminal_direct_chromatic_shape(self) -> None:
        shape = self._shape(287, (255, 85, 0, 255))
        masks = _resolve_masks(self._group([shape]), terminal_state=1)
        self.assertEqual(masks[id(shape)], (True, ("section_terminal_state_01",)))

    def test_unknown_terminal_state_value_fails_closed(self) -> None:
        shape = self._shape(287, (255, 255, 255, 255))
        with self.assertRaises(FlattenError):
            _resolve_masks(self._group([shape]), terminal_state=2)


if __name__ == "__main__":
    unittest.main()
