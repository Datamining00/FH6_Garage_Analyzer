from __future__ import annotations

from pathlib import Path
import unittest

from fh6garage.i18n import DEFAULT_LANGUAGE, set_language, tr


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = ROOT / "fh6garage" / "ui.py"
PARSER_SOURCE = ROOT / "fh6garage" / "parsers.py"


class I18nStage1Tests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    def test_dashboard_catalog_preserves_korean_defaults(self) -> None:
        set_language("ko")
        self.assertEqual(tr("nav.dashboard"), "대시보드")
        self.assertEqual(tr("dashboard.title"), "차고 분석 대시보드")
        self.assertEqual(tr("dashboard.by_vehicle"), "차종별 저장 콘텐츠")
        self.assertEqual(tr("db.check_update"), "업데이트 확인")
        self.assertEqual(tr("table.creator"), "제작자명")

    def test_dashboard_catalog_has_english_values(self) -> None:
        set_language("en")
        self.assertEqual(tr("nav.dashboard"), "Dashboard")
        self.assertEqual(tr("dashboard.title"), "Garage analysis dashboard")
        self.assertEqual(tr("dashboard.by_vehicle"), "Saved content by vehicle")
        self.assertEqual(tr("db.check_update"), "Check for updates")
        self.assertEqual(tr("table.creator"), "Creator")
        self.assertEqual(
            tr("common.ascending", label="Vehicle"),
            "Sort Vehicle ascending",
        )

    def test_main_ui_uses_translation_keys_for_stage1_controls(self) -> None:
        source = UI_SOURCE.read_text(encoding="utf-8")
        required = (
            'tr("nav.dashboard")',
            'tr("sidebar.always_on_top")',
            'tr("save.placeholder")',
            'tr("dashboard.title")',
            'tr("dashboard.garage_cars")',
            'tr("dashboard.by_vehicle")',
            'tr("db.check_update")',
            'tr("db.source")',
            'tr("table.vehicle")',
            'tr("table.creator")',
            'tr("common.ascending", label=label_text)',
            'tr("common.descending", label=label_text)',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)

        forbidden_stage1_literals = (
            'QCheckBox("항상 위에 표시")',
            'QPushButton("세이브 폴더 선택")',
            'QPushButton("차종별 저장 콘텐츠")',
            'QPushButton("제작자별 콘텐츠")',
            'QPushButton("업데이트 확인")',
            'QLabel("차고 차량"',
            'QLabel("차량을 선택하세요")',
        )
        for fragment in forbidden_stage1_literals:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, source)

    def test_parser_korean_patterns_are_not_translated(self) -> None:
        source = PARSER_SOURCE.read_text(encoding="utf-8")
        self.assertIn(r"차고\s*내\s*자동차\s*:\s*([0-9,]+)", source)
        self.assertIn('"운전한 시간"', source)
        self.assertIn('"경험치"', source)


if __name__ == "__main__":
    unittest.main()
