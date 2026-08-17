from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ui_path = ROOT / "source-v1.2" / "fh6garage" / "ui.py"
ui = ui_path.read_text(encoding="utf-8")
old_minimize = (
    "        if self.always_on_top_box.isChecked():\n"
    "            self.showMinimized()\n"
)
if old_minimize not in ui:
    raise SystemExit("Expected navigation minimization block was not found.")
ui_path.write_text(ui.replace(old_minimize, "", 1), encoding="utf-8")

i18n_path = ROOT / "source-v1.2" / "fh6garage" / "i18n.py"
i18n = i18n_path.read_text(encoding="utf-8")
old_tip = '''    "sidebar.always_on_top_tip": {
        "ko": "인게임 이동을 시작하면 포르자 화면을 가리지 않도록 분석기 창을 최소화합니다.",
        "en": "When in-game navigation starts, the analyzer window is minimized so it does not cover Forza.",
    },'''
new_tip = '''    "sidebar.always_on_top_tip": {
        "ko": "활성화하면 다른 창 위에 표시되며, 인게임 이동 중에도 창을 숨기지 않습니다.",
        "en": "Keep the assistant above other windows and visible during in-game navigation.",
    },'''
if old_tip not in i18n:
    raise SystemExit("Expected always-on-top tooltip block was not found.")
i18n_path.write_text(i18n.replace(old_tip, new_tip, 1), encoding="utf-8")

test_path = ROOT / "source-v1.2" / "tests" / "test_v1_3_topmost_navigation.py"
test_path.write_text(
    '''from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class V13TopmostNavigationTests(unittest.TestCase):
    def test_navigation_does_not_minimize_always_on_top_window(self) -> None:
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        legacy = "if self.always_on_top_box.isChecked():\\n            self.showMinimized()"
        self.assertNotIn(legacy, source)

    def test_always_on_top_tooltip_matches_new_behavior(self) -> None:
        source = (ROOT / "fh6garage" / "i18n.py").read_text(encoding="utf-8")
        self.assertIn("인게임 이동 중에도 창을 숨기지 않습니다", source)
        self.assertNotIn("분석기 창을 최소화합니다", source)


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)
