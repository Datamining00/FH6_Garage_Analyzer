from __future__ import annotations

import unittest

from fh6garage.preview3d.strict_livery_default_patch import (
    ensure_hybrid_livery_option,
    select_legacy_livery_default,
    select_strict_livery_default,
)


class _FakeCombo:
    def __init__(self, current: str, values: tuple[str, ...] = ("legacy", "strict", "declared_confirmed")):
        self.values = list(values)
        self.labels = list(values)
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

    def addItem(self, label, value):
        self.labels.append(str(label))
        self.values.append(value)


class _FakeStatus:
    def __init__(self):
        self.text = ""

    def setText(self, value):
        self.text = str(value)


class LegacyLiveryDefaultPatchTests(unittest.TestCase):
    def test_initial_strict_selection_is_restored_to_legacy(self):
        combo = _FakeCombo("strict")
        status = _FakeStatus()
        changed = select_legacy_livery_default({"eligibility": combo, "status": status})
        self.assertTrue(changed)
        self.assertEqual(combo.currentData(), "legacy")
        self.assertIn("Legacy", status.text)

    def test_existing_legacy_selection_stays_legacy(self):
        combo = _FakeCombo("legacy")
        status = _FakeStatus()
        changed = select_legacy_livery_default({"eligibility": combo, "status": status})
        self.assertFalse(changed)
        self.assertEqual(combo.currentData(), "legacy")
        self.assertIn("Legacy", status.text)

    def test_compatibility_alias_now_follows_legacy_default(self):
        combo = _FakeCombo("strict")
        changed = select_strict_livery_default({"eligibility": combo})
        self.assertTrue(changed)
        self.assertEqual(combo.currentData(), "legacy")

    def test_hybrid_option_is_added_without_changing_current_selection(self):
        combo = _FakeCombo("legacy")
        changed = ensure_hybrid_livery_option({"eligibility": combo})
        self.assertTrue(changed)
        self.assertEqual(combo.currentData(), "legacy")
        self.assertGreaterEqual(combo.findData("hybrid"), 0)

    def test_existing_hybrid_option_is_not_duplicated(self):
        combo = _FakeCombo("legacy", ("legacy", "strict", "declared_confirmed", "hybrid"))
        changed = ensure_hybrid_livery_option({"eligibility": combo})
        self.assertFalse(changed)
        self.assertEqual(combo.values.count("hybrid"), 1)

    def test_missing_legacy_choice_fails_closed(self):
        combo = _FakeCombo("strict", ("strict", "declared_confirmed"))
        changed = select_legacy_livery_default({"eligibility": combo})
        self.assertFalse(changed)
        self.assertEqual(combo.currentData(), "strict")


if __name__ == "__main__":
    unittest.main()
