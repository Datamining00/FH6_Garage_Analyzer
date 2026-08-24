from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QWidget

from fh6garage.creator_aliases import CreatorAliasStore
from fh6garage import v1_3_2_alias_manager_change_card_fix as fix


class _DummyWindow(QWidget):
    def __init__(self, alias_path: Path) -> None:
        super().__init__()
        self.creator_aliases = CreatorAliasStore(alias_path)
        self.result = None
        self._fh6_alias_dialog = None


class AliasManagerChangeCardFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_deleted_heading_is_removed_and_archive_uses_panel_frame(self) -> None:
        root = QWidget()
        card = QFrame(root)
        card.setObjectName("card")
        card.setProperty("fh6ArchiveCard", True)
        label = QLabel("삭제 전", card)
        label.show()

        fix._remove_deleted_heading_and_match_main_frame(root)
        self.assertEqual(card.objectName(), "panel")
        self.assertFalse(label.isVisible())

    def test_alias_dialog_is_nonmodal_and_initial_inputs_are_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            window = _DummyWindow(Path(temp) / "creator_aliases.json")
            old_observed = fix._alias._observed_creator_names
            old_refresh = fix._alias._refresh_alias_views
            try:
                fix._alias._observed_creator_names = lambda _window: ["OldName", "NewName"]
                fix._alias._refresh_alias_views = lambda _window: None
                fix._open_alias_dialog_nonmodal(window)
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
                fix._alias._observed_creator_names = old_observed
                fix._alias._refresh_alias_views = old_refresh

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

    def test_patch_order_keeps_thread_affinity_final(self) -> None:
        source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        alias_pos = source.find("apply_v1_3_2_alias_manager_change_card_fix(MainWindow)")
        final_pos = source.find("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertGreaterEqual(alias_pos, 0)
        self.assertGreater(final_pos, alias_pos)


if __name__ == "__main__":
    unittest.main()
