from __future__ import annotations

import struct
import unittest
from pathlib import Path

from fh6garage.livery_bare_parent_transform_fix import (
    _EXTENDED_CHILD_MARKER,
    _bare_parent_transform_candidate,
    apply_livery_bare_parent_transform_fix,
)
from fh6garage.livery_preview import _load_backend


def _transform(x: float, y: float, scale: float, rotation: float) -> bytes:
    return struct.pack("<4f", x, y, scale, rotation)


def _counted_group(count: int) -> bytes:
    blocks = (int(count) + 7) // 8
    return b"\x20" + struct.pack("<HH", int(count), blocks) + b"\x00\x00" + bytes(blocks)


def _shape(shape_id: int, x: float, y: float) -> bytes:
    return (
        b"\x00\x02"
        + struct.pack("<H", int(shape_id))
        + struct.pack("<6f", 0.0, x, y, 1.0, 1.0, 0.0)
        + bytes((0, 0, 255, 255))
    )


class BareParentTransformFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decoder, _renderer = _load_backend()
        apply_livery_bare_parent_transform_fix()

    def _pair_stream(self) -> bytes:
        parent = _transform(100.0, 20.0, 1.0, 0.0)
        child_one = _EXTENDED_CHILD_MARKER + _transform(10.0, 2.0, 1.0, 0.0)
        group_one = _counted_group(2) + _shape(101, 0.0, 0.0) + _shape(102, 5.0, 0.0)
        child_two = b"\x00" + _transform(-20.0, -3.0, 1.0, 0.0)
        group_two = _counted_group(2) + _shape(103, 0.0, 0.0) + _shape(104, -5.0, 0.0)
        return parent + child_one + group_one + child_two + group_two

    def test_candidate_requires_bare_parent_before_proven_extended_child(self):
        data = self._pair_stream()
        transform = _bare_parent_transform_candidate(self.decoder, data, 0, len(data))
        self.assertIsNotNone(transform)
        self.assertAlmostEqual(transform.x, 100.0)
        self.assertAlmostEqual(transform.y, 20.0)

        ordinary = _EXTENDED_CHILD_MARKER + _transform(10.0, 2.0, 1.0, 0.0) + _counted_group(2)
        self.assertIsNone(_bare_parent_transform_candidate(self.decoder, ordinary, 0, len(ordinary)))

    def test_walk_step_wraps_two_child_groups_in_bare_parent_transform(self):
        decoder = self.decoder
        data = self._pair_stream()
        root = decoder.GroupNode(source="test_root", section="Right")
        state = decoder.WalkState(stack=[root])
        pos = 0
        guard = 0
        while pos < len(data) and guard < 128:
            guard += 1
            decoder.close_complete_stack(state.stack)
            next_pos = decoder.walk_step(
                data,
                pos,
                len(data),
                state,
                livery=True,
                livery_invert_odd_rotation=True,
            )
            self.assertGreater(next_pos, pos)
            pos = next_pos
        decoder.close_complete_stack(state.stack)

        self.assertEqual(state.decoded_shapes, 4)
        self.assertEqual(len(root.items), 1)
        parent = root.items[0]
        self.assertIsInstance(parent, decoder.GroupNode)
        self.assertEqual(parent.source, "implicit_bare_transform_pair")
        self.assertEqual(parent.expected_children, 2)
        self.assertEqual(len(parent.items), 2)
        self.assertAlmostEqual(parent.transform.x, 100.0)
        self.assertAlmostEqual(parent.transform.y, 20.0)

        flat = decoder.flatten_tree(root, section="Right")
        self.assertEqual(len(flat), 4)
        self.assertAlmostEqual(flat[0]["data"][0], 110.0, places=5)
        self.assertAlmostEqual(flat[0]["data"][1], 22.0, places=5)
        self.assertAlmostEqual(flat[2]["data"][0], 80.0, places=5)
        self.assertAlmostEqual(flat[2]["data"][1], 17.0, places=5)

    def test_app_installs_fix_after_decoder_recovery(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        if "apply_kfps_3_1_31_clean_baseline()" in text:
            self.assertNotIn("apply_livery_decoder_recovery_patch()", text)
            self.assertNotIn("apply_livery_bare_parent_transform_fix()", text)
            return
        recovery_pos = text.index("apply_livery_decoder_recovery_patch()")
        fix_pos = text.index("apply_livery_bare_parent_transform_fix()")
        baseline_pos = text.index("apply_livery_baseline_behavior_patch()")
        self.assertGreater(fix_pos, recovery_pos)
        self.assertLess(fix_pos, baseline_pos)


if __name__ == "__main__":
    unittest.main()
