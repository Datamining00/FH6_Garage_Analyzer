from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from fh6garage.v1_3_2_release_layout_patch import (
    _align_left_actions_to_right_second_third,
    _compact_change_banner,
    _move_change_banner_to_reserved_slot,
)


ROOT = Path(__file__).resolve().parents[1]


class _Aligner:
    def __init__(self) -> None:
        self.fourth_button = None
        self.fifth_button = None
        self.calls = 0

    def reposition(self) -> None:
        self.calls += 1


class ReleaseLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_refresh_banner_moves_into_reserved_slot(self) -> None:
        content = QWidget()
        content_layout = QVBoxLayout(content)
        banner = QFrame(content)
        row = QHBoxLayout(banner)
        label = QLabel("long summary", banner)
        view = QPushButton("View", banner)
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(view)
        content_layout.addWidget(banner)

        slot = QWidget(content)
        content_layout.addWidget(slot)
        owner = SimpleNamespace(
            refresh_diff_banner=banner,
            refresh_diff_banner_label=label,
            refresh_diff_view_button=view,
            _fh6_v132_reserved_backup_slot=slot,
        )

        _move_change_banner_to_reserved_slot(owner)

        self.assertIs(banner.parentWidget(), slot)
        self.assertIsNotNone(slot.layout())
        self.assertGreaterEqual(slot.layout().indexOf(banner), 0)
        self.assertTrue(label.isHidden())

    def test_change_banner_is_compact_and_hidden_when_no_change(self) -> None:
        banner = QFrame()
        view = QPushButton()
        owner = SimpleNamespace(
            refresh_diff_banner=banner,
            refresh_diff_view_button=view,
            _fh6_latest_livery_diff=SimpleNamespace(
                baseline=False,
                total=6,
                added=[1, 2, 3],
                removed=[1],
                changed=[1, 2],
            ),
        )
        _compact_change_banner(owner)
        self.assertEqual(view.text(), "+3  −1  ~2")
        self.assertIn("추가 3", view.toolTip())
        self.assertFalse(banner.isHidden())

        owner._fh6_latest_livery_diff = SimpleNamespace(
            baseline=False,
            total=0,
            added=[],
            removed=[],
            changed=[],
        )
        _compact_change_banner(owner)
        self.assertTrue(banner.isHidden())

    def test_hide_and_info_retarget_right_second_and_third_rows(self) -> None:
        triangle = QToolButton()
        excluded = QToolButton()
        aligner = _Aligner()
        card = SimpleNamespace(
            _fh6_card_action_aligner=aligner,
            _fh6_triangle_box=triangle,
            _fh6_excluded_box=excluded,
        )
        _align_left_actions_to_right_second_third(card)
        QApplication.processEvents()
        self.assertIs(aligner.fourth_button, triangle)
        self.assertIs(aligner.fifth_button, excluded)
        self.assertGreaterEqual(aligner.calls, 1)

    def test_release_patch_stays_before_window_creation(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        release_layout = "apply_v1_3_2_release_layout_patch(MainWindow)"
        thread_fix = "window = MainWindow(project_root=root)"
        self.assertIn(release_layout, source)
        self.assertIn(thread_fix, source)
        self.assertLess(source.index(release_layout), source.index(thread_fix))

    def test_portable_spec_exists(self) -> None:
        spec = ROOT / "FH6_Assistant_v1.3.2_portable.spec"
        self.assertTrue(spec.is_file())
        text = spec.read_text(encoding="utf-8")
        self.assertIn("exclude_binaries=True", text)
        self.assertIn("COLLECT(", text)


if __name__ == "__main__":
    unittest.main()
