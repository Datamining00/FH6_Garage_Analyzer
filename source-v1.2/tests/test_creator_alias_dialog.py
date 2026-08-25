from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QWidget

from fh6garage.creator_aliases import CreatorAliasStore
from fh6garage import change_dialog_cards
from fh6garage import creator_alias_dialog


class _DummyWindow(QWidget):
    def __init__(self, alias_path: Path) -> None:
        super().__init__()
        self.creator_aliases = CreatorAliasStore(alias_path)
        self.result = None
        self._fh6_alias_dialog = None


class CreatorAliasDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_deleted_card_presentation_is_integrated_at_creation(self) -> None:
        source = inspect.getsource(change_dialog_cards._single_change_item)
        self.assertIn('_archive_card_like_main(window, change.before, "", card_width)', source)

        archive_source = inspect.getsource(change_dialog_cards._archive_card_like_main)
        self.assertIn('card.setObjectName("panel" if not heading else "card")', archive_source)
        self.assertIn("if heading:", archive_source)

    def test_alias_dialog_is_nonmodal_and_initial_inputs_are_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            window = _DummyWindow(Path(temp) / "creator_aliases.json")
            old_observed = creator_alias_dialog._alias.observed_creator_names
            old_refresh = creator_alias_dialog._alias.refresh_alias_views
            try:
                creator_alias_dialog._alias.observed_creator_names = lambda _window: ["OldName", "NewName"]
                creator_alias_dialog._alias.refresh_alias_views = lambda _window: None
                creator_alias_dialog.open_creator_alias_dialog(window)
                dialog = window._fh6_alias_dialog
                self.assertIsInstance(dialog, QDialog)
                self.assertFalse(dialog.isModal())
                self.assertTrue(dialog.isVisible())
                self.assertEqual(dialog._fh6_alias_source.currentText(), "")
                self.assertEqual(dialog._fh6_alias_target.currentText(), "")
                self.assertEqual(dialog._fh6_alias_link_button.text(), "이름 연결")
                self.assertEqual(dialog._fh6_alias_unlink_button.text(), "연결 해제")
                dialog.close()
                self.app.processEvents()
            finally:
                creator_alias_dialog._alias.observed_creator_names = old_observed
                creator_alias_dialog._alias.refresh_alias_views = old_refresh

    def test_selected_group_unlink_dissolves_only_that_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = CreatorAliasStore(Path(temp) / "creator_aliases.json")
            store.merge("A", "B")
            store.merge("B", "C")
            store.merge("X", "Y")
            target = store.find_group("C")
            self.assertEqual(target.all_names(), ["C", "B", "A"])

            for name in list(target.all_names()[1:]):
                store.split(name)

            self.assertEqual(store.group_for("A").all_names(), ["A"])
            self.assertEqual(store.group_for("B").all_names(), ["B"])
            self.assertEqual(store.group_for("C").all_names(), ["C"])
            self.assertEqual(store.group_for("Y").all_names(), ["Y", "X"])

    def test_runtime_patch_is_no_longer_applied(self) -> None:
        source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_alias_manager_change_card_fix", source)


if __name__ == "__main__":
    unittest.main()
