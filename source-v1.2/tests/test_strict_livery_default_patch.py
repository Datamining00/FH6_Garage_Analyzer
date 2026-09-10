from __future__ import annotations

import unittest

from fh6garage.preview3d.strict_livery_default_patch import select_strict_livery_default


class _FakeCombo:
    def __init__(self, current: str, values: tuple[str, ...] = ("legacy", "strict", "declared_confirmed")):
        self.values = list(values)
        self.index = self.values.index(current) if current in self.values else -1

    def currentData(self):
        return self.values[self.index] if self.index >= 0 else None

    def findData(self, value):
        try:
            return self.values.index(value)
        except ValueError:
            return -1

    def setCurrentIndex(self, index):
        self.index = int(index)


class _FakeStatus:
    def __init__(self):
        self.text = ""

    def setText(self, value):
        self.text = str(value)


class StrictLiveryDefaultPatchTests(unittest.TestCase):
    def test_initial_legacy_selection_is_promoted_to_strict(self):
        combo = _FakeCombo("legacy")
        status = _FakeStatus()
        changed = select_strict_livery_default({"eligibility": combo, "status": status})
        self.assertTrue(changed)
        self.assertEqual(combo.currentData(), "strict")
        self.assertIn("Strict", status.text)

    def test_explicit_nonlegacy_selection_is_preserved(self):
        combo = _FakeCombo("declared_confirmed")
        changed = select_strict_livery_default({"eligibility": combo})
        self.assertFalse(changed)
        self.assertEqual(combo.currentData(), "declared_confirmed")

    def test_missing_strict_choice_fails_closed_without_changing_legacy(self):
        combo = _FakeCombo("legacy", ("legacy", "declared_confirmed"))
        changed = select_strict_livery_default({"eligibility": combo})
        self.assertFalse(changed)
        self.assertEqual(combo.currentData(), "legacy")


if __name__ == "__main__":
    unittest.main()
