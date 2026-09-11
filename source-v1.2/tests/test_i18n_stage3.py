from __future__ import annotations

from pathlib import Path
import unittest

from fh6garage.game_navigation import GameGridSession, GameNavigationError
from fh6garage.i18n import DEFAULT_LANGUAGE, set_language, tr

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
CAR_DB = (ROOT / "fh6garage" / "car_db.py").read_text(encoding="utf-8")
GAME_NAV = (ROOT / "fh6garage" / "game_navigation.py").read_text(encoding="utf-8")
SCANNER = (ROOT / "fh6garage" / "scanner.py").read_text(encoding="utf-8")

class I18nStage3Tests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    def test_navigation_runtime_errors_follow_language(self) -> None:
        set_language("ko")
        with self.assertRaisesRegex(GameNavigationError, "이동 가능한 항목"):
            GameGridSession([]).plan_to("missing")
        set_language("en")
        with self.assertRaisesRegex(GameNavigationError, "no items available"):
            GameGridSession([]).plan_to("missing")

    def test_stage3_catalog_english(self) -> None:
        set_language("en")
        self.assertEqual(tr("common.cancel"), "Cancel")
        self.assertEqual(tr("memo.saved"), "Memo saved")
        self.assertEqual(tr("image.fit"), "Fit")
        self.assertEqual(tr("db.update_failed"), "Vehicle database update failed")
        self.assertIn("1229", tr("db.name_empty_message", car_id=1229))

    def test_ui_uses_stage3_translation_keys(self) -> None:
        for fragment in (
            'tr("navigation.dialog_title")',
            'tr("navigation.auto_activate")',
            'tr("status.toggle_check")',
            'tr("preview.enlarge")',
            'tr("memo.saved")',
            'tr("db.update_prompt")',
            'tr("db.override_title")',
            'tr("image.hint")',
            'tr("dashboard.search_creator")',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, UI)

    def test_error_modules_are_i18n_aware(self) -> None:
        self.assertIn('from .i18n import tr', CAR_DB)
        self.assertIn('tr("car_db.download_failed"', CAR_DB)
        self.assertIn('from .i18n import tr', GAME_NAV)
        self.assertIn('tr("navigation.window_not_found")', GAME_NAV)
        self.assertIn('from .i18n import tr', SCANNER)
        self.assertIn('tr("scanner.containers_missing")', SCANNER)

    def test_major_user_facing_literals_removed(self) -> None:
        for fragment in (
            'QMessageBox.information(self, "제작자 정보 없음"',
            'dialog.setWindowTitle("리버리 정보")',
            'dialog.setWindowTitle("차량명 사용자 오버라이드")',
            'setToolTip("체크 상태 전환")',
            'setToolTip("미리보기 크게 보기")',
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, UI)

if __name__ == "__main__":
    unittest.main()
