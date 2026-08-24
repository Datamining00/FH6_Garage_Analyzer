from __future__ import annotations

from pathlib import Path
import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton, QVBoxLayout, QWidget

from fh6garage import v1_3_2_change_dialog_folder_patch as feature
from fh6garage import v1_3_2_change_dialog_runtime_fix as runtime_fix
from fh6garage.v1_3_2_card_alignment_patch import _CardActionAligner
from fh6garage.v1_3_2_ui_cleanup_patch import _HideButtonAligner


ROOT = Path(__file__).resolve().parents[1]


class ChangeDialogRuntimeFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_runtime_fix_stays_before_thread_affinity_finalizer(self) -> None:
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        feature_pos = app.index("apply_v1_3_2_change_dialog_folder_patch(MainWindow)")
        runtime_pos = app.index("apply_v1_3_2_change_dialog_runtime_fix(MainWindow)")
        thread_pos = app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(feature_pos, runtime_pos)
        self.assertLess(runtime_pos, thread_pos)

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

        calls: list[object] = []
        original = feature._open_change_dialog_same_as_main
        feature._open_change_dialog_same_as_main = lambda owner: calls.append(owner)
        try:
            runtime_fix._repair_change_button(window)
            self.assertFalse(
                slot.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            )
            self.assertTrue(view.isEnabled())
            view.click()
            self.assertEqual(calls, [window])
        finally:
            feature._open_change_dialog_same_as_main = original
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

        hide_aligner = _HideButtonAligner(overlay, hide, zoom, info)
        card_aligner = _CardActionAligner(
            overlay, hide, info, move, zoom, memo
        )
        four_aligner = feature._FourLeftActionAligner(card, overlay)
        card._fh6_hide_aligner = hide_aligner
        card._fh6_card_action_aligner = card_aligner
        card._fh6_four_left_action_aligner = four_aligner

        overlay.show()
        self.app.processEvents()
        runtime_fix._repoint_legacy_aligners(card)

        # Exercise every aligner, including the two legacy ones, then make the
        # four-row owner run last exactly as the runtime fix does.
        runtime_fix._force_card_action_geometry(card)

        self.assertIs(hide_aligner.target_button, triangle)
        self.assertIs(card_aligner.fourth_button, triangle)
        self.assertIs(card_aligner.fifth_button, excluded)
        self.assertEqual(move.geometry().center().y(), check.geometry().center().y())
        self.assertEqual(hide.geometry().center().y(), triangle.geometry().center().y())
        self.assertEqual(info.geometry().center().y(), excluded.geometry().center().y())
        self.assertEqual(folder.geometry().center().y(), zoom.geometry().center().y())

        overlay.close()
        overlay.deleteLater()
        card.deleteLater()


if __name__ == "__main__":
    unittest.main()
