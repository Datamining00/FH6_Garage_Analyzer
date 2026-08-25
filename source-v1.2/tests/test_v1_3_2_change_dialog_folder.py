from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from fh6garage import change_dialog_cards as patch

ROOT = Path(__file__).resolve().parents[1]


class ChangeDialogFolderPatchTests(unittest.TestCase):
    def test_runtime_patch_is_removed(self) -> None:
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_change_dialog_folder_patch(MainWindow)", app)
        self.assertFalse(
            (ROOT / "fh6garage" / "v1_3_2_change_dialog_folder_patch.py").exists()
        )

    def test_change_view_is_a_main_sized_standalone_window(self) -> None:
        source = inspect.getsource(patch._open_change_dialog_same_as_main)
        self.assertIn("QDialog(window, Qt.WindowType.Window)", source)
        self.assertIn("dialog.setModal(False)", source)
        self.assertIn("dialog.resize(window.size())", source)
        self.assertIn("_main_livery_card_width(window)", source)
        self.assertIn("_main_livery_columns(window)", source)

    def test_four_left_rows_match_requested_right_rows(self) -> None:
        source = inspect.getsource(patch._FourLeftActionAligner.reposition)
        self.assertIn('(\"_fh6_game_move_button\", \"_fh6_check_box\")', source)
        self.assertIn('(\"_fh6_hide_button\", \"_fh6_triangle_box\")', source)
        self.assertIn('(\"_fh6_info_button\", \"_fh6_excluded_box\")', source)
        self.assertIn('(\"_fh6_folder_button\", \"_fh6_zoom_button\")', source)

    def test_folder_action_only_opens_existing_container_directory(self) -> None:
        source = inspect.getsource(patch._open_record_folder)
        self.assertIn("path.is_dir()", source)
        self.assertIn("QDesktopServices.openUrl", source)
        self.assertNotIn("unlink", source)
        self.assertNotIn("remove(", source)
        self.assertNotIn("rmtree", source)

    def test_folder_button_uses_release_icon_geometry(self) -> None:
        self.assertEqual(patch.CARD_ACTION_BUTTON_SIZE, 30)
        self.assertEqual(patch.CARD_ACTION_ICON_SIZE, 20)
        source = inspect.getsource(patch._install_folder_button)
        self.assertIn("SP_DirOpenIcon", source)
        self.assertIn("_fh6_folder_button", source)

    def test_deleted_archive_card_remains_actionless(self) -> None:
        source = inspect.getsource(patch._archive_card_like_main)
        self.assertIn('card.setProperty("fh6ArchiveCard", True)', source)
        self.assertNotIn("_install_folder_button", source)
        self.assertNotIn("_fh6_game_move_button", source)
        self.assertNotIn("_fh6_hide_button", source)

    def test_columns_remain_clamped_to_two_through_four(self) -> None:
        class Dummy:
            def __init__(self, value: int) -> None:
                self.value = value

            def _fh6_grid_column_count(self, _content_type: str) -> int:
                return self.value

        self.assertEqual(patch._main_livery_columns(Dummy(1)), 2)
        self.assertEqual(patch._main_livery_columns(Dummy(3)), 3)
        self.assertEqual(patch._main_livery_columns(Dummy(9)), 4)


if __name__ == "__main__":
    unittest.main()
