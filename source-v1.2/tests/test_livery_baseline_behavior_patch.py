from __future__ import annotations

import unittest
from types import SimpleNamespace

from fh6garage.livery_baseline_behavior_patch import (
    _ALLOWED_SCALES,
    _section_state,
    normalize_decoded_layer_order,
)


SECTIONS = ("Front", "Back", "Top", "Left", "Right")


class BaselineBehaviorPatchTests(unittest.TestCase):
    def test_requested_section_shortage_is_partial(self) -> None:
        expected = {name: 0 for name in SECTIONS}
        expected["Right"] = 3000
        decoded = {name: () for name in SECTIONS}
        decoded["Right"] = tuple({"source_offset": index * 32} for index in range(2997))
        state = _section_state(expected, decoded, "Right", SECTIONS)
        self.assertEqual(state[:4], ("partial", "Right", 3000, 2997))

    def test_earlier_section_shortage_still_blocks_later_section(self) -> None:
        expected = {name: 0 for name in SECTIONS}
        expected["Left"] = 3000
        expected["Right"] = 3000
        decoded = {name: () for name in SECTIONS}
        decoded["Left"] = tuple({"source_offset": index * 32} for index in range(2997))
        decoded["Right"] = tuple({"source_offset": 200000 + index * 32} for index in range(3000))
        state = _section_state(expected, decoded, "Right", SECTIONS)
        self.assertEqual(state, ("fatal", "Left", 3000, 2997, True))

    def test_overdecoded_requested_section_is_not_partial(self) -> None:
        expected = {name: 0 for name in SECTIONS}
        expected["Right"] = 3000
        decoded = {name: () for name in SECTIONS}
        decoded["Right"] = tuple({"source_offset": index * 32} for index in range(3001))
        state = _section_state(expected, decoded, "Right", SECTIONS)
        self.assertEqual(state, ("fatal", "Right", 3000, 3001, False))

    def test_source_offsets_define_stable_render_order(self) -> None:
        first = {"source_section": "Right", "source_offset": 96, "name": "third"}
        second = {"source_section": "Right", "source_offset": 32, "name": "first"}
        third = {"source_section": "Right", "source_offset": 64, "name": "second"}
        decoded = SimpleNamespace(layers=[first, second, third], report={})
        decoded, changed = normalize_decoded_layer_order(decoded, ("Right",))
        self.assertEqual([item["name"] for item in decoded.layers], ["first", "second", "third"])
        self.assertEqual(changed, ("Right",))

    def test_missing_offset_keeps_decoder_order(self) -> None:
        layers = [
            {"source_section": "Right", "source_offset": 96, "name": "a"},
            {"source_section": "Right", "source_offset": None, "name": "b"},
            {"source_section": "Right", "source_offset": 32, "name": "c"},
        ]
        decoded = SimpleNamespace(layers=list(layers), report={})
        decoded, changed = normalize_decoded_layer_order(decoded, ("Right",))
        self.assertEqual([item["name"] for item in decoded.layers], ["a", "b", "c"])
        self.assertEqual(changed, ())

    def test_one_x_is_a_persistable_scale(self) -> None:
        self.assertEqual(_ALLOWED_SCALES, (1, 2, 4, 8, 16))


if __name__ == "__main__":
    unittest.main()
