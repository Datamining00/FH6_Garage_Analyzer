from __future__ import annotations

from pathlib import Path
import unittest

from fh6garage.i18n import DEFAULT_LANGUAGE, set_language, tr


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = ROOT / "fh6garage" / "ui.py"


class I18nStage2Tests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    def test_saved_content_catalog_preserves_korean_defaults(self) -> None:
        set_language("ko")
        self.assertEqual(tr("content.sort_label"), "정렬:")
        self.assertEqual(tr("content.group_vehicle"), "동일 차량끼리 묶기")
        self.assertEqual(tr("table.downloaded"), "다운로드일")
        self.assertEqual(tr("status.none"), "분류 없음")
        self.assertEqual(tr("detail.tuning_title"), "튜닝 세부 정보")

    def test_saved_content_catalog_has_english_values(self) -> None:
        set_language("en")
        self.assertEqual(tr("dashboard.saved_livery"), "Saved liveries")
        self.assertEqual(tr("dashboard.saved_tuning"), "Saved tunings")
        self.assertEqual(tr("content.sort_brand"), "Brand")
        self.assertEqual(tr("content.group_vehicle"), "Group by vehicle")
        self.assertEqual(tr("table.description"), "Description")
        self.assertEqual(tr("status.duplicate_livery_only"), "Duplicate liveries only")
        self.assertEqual(tr("detail.tuning_title"), "Tuning details")
        self.assertEqual(
            tr("content.group_header", vehicle="2008 Mazda Furai", noun="liveries", count=2),
            "2008 Mazda Furai · 2 liveries",
        )

    def test_stage2_ui_uses_translation_keys(self) -> None:
        source = UI_SOURCE.read_text(encoding="utf-8")
        required = (
            'tr("dashboard.saved_livery")',
            'tr("dashboard.saved_tuning")',
            'tr("table.tuning_name")',
            'tr("table.status")',
            'tr("content.search_placeholder")',
            'tr("content.sort_label")',
            'tr("content.group_vehicle")',
            'tr("status.filter_tip")',
            'tr("scan.loading")',
            'tr("scan.failed_title")',
            'tr("content.group_header"',
            'tr("detail.tuning_title")',
            'tr("detail.installed_parts")',
            'tr("detail.tuning_values")',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)

    def test_selected_stage2_hardcoded_literals_are_removed(self) -> None:
        source = UI_SOURCE.read_text(encoding="utf-8")
        forbidden = (
            'self._saved_content_table("리버리 이름")',
            'self._saved_content_table("튜닝 이름")',
            'QLabel("정렬:")',
            'QPushButton("동일 차량끼리 묶기")',
            'self._begin_busy("세이브와 썸네일을 불러오는 중…")',
            'QMessageBox.critical(self, "세이브 스캔 실패", message)',
            'dialog.setWindowTitle("튜닝 세부 정보")',
            '"[장착 부품 ID]"',
            '"[세부 튜닝 값]"',
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
