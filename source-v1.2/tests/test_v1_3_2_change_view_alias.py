from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PySide6.QtWidgets import QApplication, QPushButton, QToolButton

from fh6garage.creator_aliases import CreatorAliasStore
from fh6garage.refresh_history import LiverySnapshotEntry
from fh6garage.v1_3_2_change_view_alias_patch import _archive_card


_APP = QApplication.instance() or QApplication([])


class _ArchiveWindow:
    def __init__(self, store: CreatorAliasStore):
        self.creator_aliases = store

    @staticmethod
    def _car_label(car_id):
        return f"Car {car_id}"


class CreatorAliasStoreTests(unittest.TestCase):
    def test_transitive_merge_moves_entire_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CreatorAliasStore(Path(tmp) / "creator_aliases.json")
            store.merge("A", "B")
            group = store.merge("B", "C")

            self.assertEqual(group.current, "C")
            self.assertEqual(group.previous, ["B", "A"])
            for name in ("A", "B", "C"):
                self.assertEqual(store.canonical_name(name), "C")
                self.assertEqual(store.search_names(name), ["C", "B", "A"])
            self.assertEqual(store.display_name("A"), "C (B, A)")

    def test_merging_two_existing_groups_keeps_both_histories(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CreatorAliasStore(Path(tmp) / "creator_aliases.json")
            store.merge("A1", "A")
            store.merge("B1", "B")
            group = store.merge("A", "B")

            self.assertEqual(group.current, "B")
            self.assertEqual(group.previous, ["A", "A1", "B1"])
            self.assertEqual(store.canonical_name("A1"), "B")
            self.assertEqual(store.canonical_name("B1"), "B")

    def test_split_detaches_only_selected_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CreatorAliasStore(Path(tmp) / "creator_aliases.json")
            store.merge("A", "B")
            store.merge("B", "C")

            self.assertTrue(store.split("A"))
            self.assertEqual(store.canonical_name("A"), "A")
            self.assertEqual(store.canonical_name("B"), "C")
            self.assertEqual(store.search_names("C"), ["C", "B"])

    def test_reset_creates_backup_before_empty_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "creator_aliases.json"
            store = CreatorAliasStore(path)
            store.merge("A", "B")
            before = json.loads(path.read_text(encoding="utf-8"))

            backup = store.reset_with_backup()

            self.assertIsNotNone(backup)
            self.assertTrue(backup.is_file())
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), before)
            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(after["groups"], [])
            self.assertEqual(store.groups, [])

    def test_display_compacts_more_than_two_previous_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CreatorAliasStore(Path(tmp) / "creator_aliases.json")
            store.merge("A", "B")
            store.merge("B", "C")
            store.merge("C", "D")
            store.merge("D", "E")
            self.assertEqual(store.display_name("A"), "E (D, C +2)")

    def test_matching_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CreatorAliasStore(Path(tmp) / "creator_aliases.json")
            store.merge("OldName", "NewName")
            self.assertEqual(store.canonical_name("oldname"), "NewName")
            self.assertEqual(store.canonical_name("NEWNAME"), "NewName")


class ChangeViewContractTests(unittest.TestCase):
    def test_archived_deleted_card_has_no_action_buttons(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CreatorAliasStore(Path(tmp) / "creator_aliases.json")
            store.merge("A", "B")
            entry = LiverySnapshotEntry(
                identity="Livery:test",
                kind="Livery",
                container_name="test",
                guid="guid",
                car_id=1,
                name="Title",
                creator="A",
                description="Description",
                created="",
                decal_count=None,
                platform_code=None,
                content_sha256="hash",
                thumbnail_cache="",
            )
            card = _archive_card(_ArchiveWindow(store), entry, "삭제 전")
            self.assertTrue(bool(card.property("fh6ArchiveCard")))
            self.assertEqual(card.findChildren(QPushButton), [])
            self.assertEqual(card.findChildren(QToolButton), [])
            card.deleteLater()

    def test_app_patch_order_refresh_then_alias_then_window(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        source = app_path.read_text(encoding="utf-8")
        refresh_call = source.index("apply_v1_3_2_refresh_diff_patch(MainWindow)")
        alias_call = source.index("apply_v1_3_2_change_view_alias_patch(MainWindow)")
        thread_call = source.index("window = MainWindow(project_root=root)")
        self.assertLess(refresh_call, alias_call)
        self.assertLess(alias_call, thread_call)

    def test_change_patch_contains_zero_change_banner_suppression(self):
        patch_path = Path(__file__).resolve().parents[1] / "fh6garage" / "v1_3_2_change_view_alias_patch.py"
        source = patch_path.read_text(encoding="utf-8")
        self.assertIn("diff.total <= 0", source)
        self.assertIn("banner.hide()", source)
        self.assertIn("_fh6_open_refresh_diff_view", source)

    def test_alias_search_and_group_properties_include_all_names(self):
        patch_path = Path(__file__).resolve().parents[1] / "fh6garage" / "v1_3_2_change_view_alias_patch.py"
        source = patch_path.read_text(encoding="utf-8")
        self.assertIn("*group.all_names()", source)
        self.assertIn("creatorGroupKey", source)
        self.assertIn("creatorGroupLabel", source)
        self.assertIn("self.creator_aliases.search_names(canonical)", source)


if __name__ == "__main__":
    unittest.main()
