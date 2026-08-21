from __future__ import annotations

import unittest
from types import SimpleNamespace

from fh6garage.livery_baseline_behavior_patch import (
    _ALLOWED_SCALES,
    _section_issues,
    INACCURATE_WARNING_PREFIX,
    normalize_decoded_layer_order,
)


SECTIONS = ("Front", "Back", "Top", "Left", "Right")


class BaselineBehaviorPatchTests(unittest.TestCase):
    def test_requested_section_shortage_is_diagnostic_only(self) -> None:
        expected = {name: 0 for name in SECTIONS}
        expected["Right"] = 3000
        decoded = {name: () for name in SECTIONS}
        decoded["Right"] = tuple({"source_offset": index * 32} for index in range(2997))
        issues = _section_issues(expected, decoded, "Right", SECTIONS)
        self.assertEqual(issues, (("Right", 3000, 2997),))

    def test_earlier_section_shortage_is_also_diagnostic_not_blocking(self) -> None:
        expected = {name: 0 for name in SECTIONS}
        expected["Top"] = 2440
        expected["Right"] = 3000
        decoded = {name: () for name in SECTIONS}
        decoded["Top"] = tuple({"source_offset": index * 32} for index in range(2439))
        decoded["Right"] = tuple({"source_offset": 200000 + index * 32} for index in range(3000))
        issues = _section_issues(expected, decoded, "Right", SECTIONS)
        self.assertEqual(issues, (("Top", 2440, 2439),))

    def test_overdecoded_section_is_warning_not_gate(self) -> None:
        expected = {name: 0 for name in SECTIONS}
        expected["Right"] = 3000
        decoded = {name: () for name in SECTIONS}
        decoded["Right"] = tuple({"source_offset": index * 32} for index in range(3001))
        issues = _section_issues(expected, decoded, "Right", SECTIONS)
        self.assertEqual(issues, (("Right", 3000, 3001),))

    def test_exact_section_has_no_issue(self) -> None:
        expected = {name: 0 for name in SECTIONS}
        expected["Right"] = 3
        decoded = {name: () for name in SECTIONS}
        decoded["Right"] = ({}, {}, {})
        self.assertEqual(_section_issues(expected, decoded, "Right", SECTIONS), ())

    def test_source_offsets_do_not_override_decoder_structural_order(self) -> None:
        first = {"source_section": "Right", "source_offset": 96, "name": "structural-first"}
        second = {"source_section": "Right", "source_offset": 32, "name": "structural-second"}
        third = {"source_section": "Right", "source_offset": 64, "name": "structural-third"}
        decoded = SimpleNamespace(layers=[first, second, third], report={})
        decoded, changed = normalize_decoded_layer_order(decoded, ("Right",))
        self.assertEqual(
            [item["name"] for item in decoded.layers],
            ["structural-first", "structural-second", "structural-third"],
        )
        self.assertEqual(changed, ())
        self.assertEqual(decoded.report["fh6assistant_layer_order_policy"], "decoder_structural_dfs")

    def test_missing_offset_also_keeps_decoder_order(self) -> None:
        layers = [
            {"source_section": "Right", "source_offset": 96, "name": "a"},
            {"source_section": "Right", "source_offset": None, "name": "b"},
            {"source_section": "Right", "source_offset": 32, "name": "c"},
        ]
        decoded = SimpleNamespace(layers=list(layers), report={})
        decoded, changed = normalize_decoded_layer_order(decoded, ("Right",))
        self.assertEqual([item["name"] for item in decoded.layers], ["a", "b", "c"])
        self.assertEqual(changed, ())
        self.assertEqual(decoded.report["fh6assistant_layer_order_policy"], "decoder_structural_dfs")

    def test_one_x_is_a_persistable_scale(self) -> None:
        self.assertEqual(_ALLOWED_SCALES, (1, 2, 4, 8, 16))

    def test_inaccurate_warning_has_stable_marker(self) -> None:
        self.assertEqual(INACCURATE_WARNING_PREFIX, "[FH6_INACCURATE_PREVIEW]")


if __name__ == "__main__":
    unittest.main()
