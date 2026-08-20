from __future__ import annotations

import unittest

from fh6garage.livery_surface_order_diagnostic import build_surface_order_diagnostic


class SurfaceOrderDiagnosticTests(unittest.TestCase):
    def test_detects_left_section_reordering_and_moved_mask(self):
        left_a = {
            "source_section": "Left",
            "source_offset": 300,
            "type": 10,
            "mask": False,
            "data": [0, 0, 1, 1, 0, 0],
            "color": [255, 255, 255, 255],
        }
        left_b = {
            "source_section": "Left",
            "source_offset": 100,
            "type": 11,
            "mask": False,
            "data": [1, 0, 1, 1, 0, 0],
            "color": [255, 255, 255, 255],
        }
        left_mask = {
            "source_section": "Left",
            "source_offset": 200,
            "type": 12,
            "mask": True,
            "data": [2, 0, 1, 1, 0, 0],
            "color": [255, 255, 255, 255],
        }
        right_a = {"source_section": "Right", "source_offset": 100, "type": 20}
        right_b = {"source_section": "Right", "source_offset": 200, "type": 21}

        before = [left_a, left_b, left_mask, right_a, right_b]
        after = [left_b, left_mask, left_a, right_a, right_b]
        diagnostic = build_surface_order_diagnostic(before, after, ("Left", "Right"))

        left = diagnostic["sections"]["Left"]
        right = diagnostic["sections"]["Right"]

        self.assertTrue(left["order_changed"])
        self.assertEqual(left["moved_layer_count"], 3)
        self.assertEqual(left["moved_mask_layer_count"], 1)
        self.assertEqual(left["source_offset_descents"], 1)
        self.assertEqual(left["stacking_risk"], "high")
        self.assertFalse(right["order_changed"])
        self.assertEqual(right["stacking_risk"], "none")
        self.assertFalse(diagnostic["behavior_changed_by_diagnostic_patch"])

    def test_diagnostic_does_not_mutate_layer_order(self):
        first = {"source_section": "Left", "source_offset": 2, "type": 1}
        second = {"source_section": "Left", "source_offset": 1, "type": 2}
        before = [first, second]
        after = [second, first]
        before_ids = [id(item) for item in before]
        after_ids = [id(item) for item in after]

        build_surface_order_diagnostic(before, after, ("Left",))

        self.assertEqual([id(item) for item in before], before_ids)
        self.assertEqual([id(item) for item in after], after_ids)


if __name__ == "__main__":
    unittest.main()
