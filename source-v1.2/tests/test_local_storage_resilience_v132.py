from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fh6garage.annotations import AnnotationStore
from fh6garage.creator_aliases import CreatorAliasStore
from fh6garage.local_storage import write_json_atomic
from fh6garage.preferences import LocalPreferences


class LocalStorageResilienceTests(unittest.TestCase):
    def _blocked_path(self, root: Path, name: str) -> Path:
        blocker = root / name
        blocker.write_text("not a directory", encoding="utf-8")
        return blocker / "state.json"

    def test_preferences_remain_usable_when_disk_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = LocalPreferences(self._blocked_path(Path(temporary), "prefs"))
            store.set_bool("group", True)
            self.assertTrue(store.get_bool("group"))
            self.assertFalse(store.save())

    def test_annotations_remain_usable_when_disk_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = AnnotationStore(self._blocked_path(Path(temporary), "notes"))
            store.set_checked("item", True)
            self.assertTrue(store.get("item").checked)
            self.assertFalse(store.save())

    def test_creator_aliases_remain_usable_when_disk_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = CreatorAliasStore(self._blocked_path(Path(temporary), "aliases"))
            merged = store.merge("OldName", "CurrentName")
            self.assertEqual(merged.current, "CurrentName")
            self.assertEqual(store.canonical_name("OldName"), "CurrentName")

    def test_atomic_writer_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "state.json"
            self.assertTrue(write_json_atomic(target, {"ok": True}))
            self.assertTrue(target.is_file())
            self.assertEqual(list(root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
