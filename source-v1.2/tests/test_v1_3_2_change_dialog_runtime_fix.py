from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fh6garage import change_dialog_cards as feature
from fh6garage import card_action_alignment as actions

ROOT = Path(__file__).resolve().parents[1]


class ChangeDialogRuntimeFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_ui_cleanup_runtime_patch_is_removed(self) -> None:
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_ui_cleanup_patch(MainWindow)", app_source)
        self.assertFalse(
            (ROOT / "fh6garage" / "v1_3_2_ui_cleanup_patch.py").exists()
        )
        self.assertTrue((ROOT / "fh6garage" / "ui_cleanup.py").is_file())

    def test_runtime_fix_is_removed(self) -> None:
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_change_dialog_runtime_fix(MainWindow)", app)
        self.assertFalse(
            (ROOT / "fh6garage" / "v1_3_2_change_dialog_runtime_fix.py").exists()
        )

    def test_change_slot_becomes_mouse_enabled_and_button_opens_view(self) -> None:
        slot = QWidget()
        slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(slot)
        banner = QWidget(slot)
        banner_layout = QVBoxLayout(banner)
        view = QPushButton("+0  −1  ~0", banner)
        banner_layout.addWidget(view)
        layout.addWidget(banner)

        class Window:
            pass

        window = Window()
        window._fh6_v132_reserved_backup_slot = slot
        window.refresh_diff_banner = banner
        window.refresh_diff_view_button = view
        view.clicked.connect(
            lambda _checked=False: feature._change_view.open_change_dialog(window)
        )

        calls: list[object] = []
        original = feature._change_view.open_change_dialog
        feature._change_view.open_change_dialog = lambda owner: calls.append(owner)
        try:
            from fh6garage.release_layout import (
                _move_change_banner_to_reserved_slot,
            )

            _move_change_banner_to_reserved_slot(window)
            self.assertFalse(
                slot.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            )
            self.assertTrue(view.isEnabled())
            view.click()
            self.assertEqual(calls, [window])
        finally:
            feature._change_view.open_change_dialog = original
            slot.deleteLater()

    def test_all_retained_aligners_finish_on_requested_rows(self) -> None:
        overlay = QWidget()
        overlay.resize(620, 320)

        def button(x: int, y: int) -> QToolButton:
            control = QToolButton(overlay)
            control.setFixedSize(30, 30)
            control.move(x, y)
            control.show()
            return control

        check = button(570, 10)
        triangle = button(570, 50)
        excluded = button(570, 90)
        zoom = button(570, 130)
        memo = button(570, 170)
        move = button(10, 10)
        hide = button(10, 130)   # legacy wrong row before repair
        info = button(10, 90)
        folder = button(10, 130)

        card = QWidget()
        card._fh6_check_box = check
        card._fh6_triangle_box = triangle
        card._fh6_excluded_box = excluded
        card._fh6_zoom_button = zoom
        card._fh6_memo_button = memo
        card._fh6_game_move_button = move
        card._fh6_hide_button = hide
        card._fh6_info_button = info
        card._fh6_folder_button = folder

        aligner = actions.LiveryCardActionAligner(card, overlay)
        card._fh6_action_aligner = aligner

        overlay.show()
        self.app.processEvents()
        aligner.reposition()

        self.assertEqual(move.geometry().center().y(), check.geometry().center().y())
        self.assertEqual(hide.geometry().center().y(), triangle.geometry().center().y())
        self.assertEqual(info.geometry().center().y(), excluded.geometry().center().y())
        self.assertEqual(folder.geometry().center().y(), zoom.geometry().center().y())

        overlay.close()
        overlay.deleteLater()
        card.deleteLater()


if __name__ == "__main__":
    unittest.main()
