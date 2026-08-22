from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class V13TopmostNavigationTests(unittest.TestCase):
    def test_navigation_does_not_minimize_always_on_top_window(self) -> None:
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        legacy = "if self.always_on_top_box.isChecked():\n            self.showMinimized()"
        self.assertNotIn(legacy, source)

    def test_always_on_top_tooltip_matches_new_behavior(self) -> None:
        source = (ROOT / "fh6garage" / "i18n.py").read_text(encoding="utf-8")
        self.assertIn("인게임 이동 중에도 창을 숨기지 않습니다", source)
        self.assertNotIn("분석기 창을 최소화합니다", source)


if __name__ == "__main__":
    unittest.main()
