from __future__ import annotations

import unittest

from fh6garage.livery_left_2761_exclusion_test import (
    filter_probe_target,
    is_probe_target,
)


class Left2761ExclusionDiagnosticTests(unittest.TestCase):
    def _target(self):
        return {
            "source_section": "Left",
            "source_offset": 185644,
            "type": 1048677,
            "mask": False,
        }

    def test_exact_probe_signature_is_selected(self):
        self.assertTrue(is_probe_target(self._target()))

    def test_mask_or_other_section_is_not_selected(self):
        masked = dict(self._target(), mask=True)
        right = dict(self._target(), source_section="Right")
        self.assertFalse(is_probe_target(masked))
        self.assertFalse(is_probe_target(right))

    def test_filter_removes_only_exact_probe_target(self):
        before = {"source_section": "Left", "source_offset": 185612, "type": 1048911, "mask": False}
        target = self._target()
        after = {"source_section": "Right", "source_offset": 185644, "type": 1048677, "mask": False}
        kept, removed = filter_probe_target([before, target, after])
        self.assertEqual(removed, 1)
        self.assertEqual(kept, [before, after])


if __name__ == "__main__":
    unittest.main()
