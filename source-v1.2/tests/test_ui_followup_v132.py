from __future__ import annotations

import sys
import unittest

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fh6garage.v1_3_2_ui_followup_patch import (
    _align_path_rows,
    _configure_livery_source_switch,
)


class _PathHost(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self.path_edit = QLineEdit(self)
        self.save_choose = QPushButton("세이브 폴더 선택", self)
        self.refresh = QPushButton("전체 새로고침", self)
        save_row.addWidget(self.path_edit, 1)
        save_row.addWidget(self.save_choose)
        save_row.addWidget(self.refresh)
        root.addLayout(save_row)

        cache_row = QHBoxLayout()
        cache_row.setSpacing(8)
        self.cache_path_edit = QLineEdit(self)
        self.cache_choose = QPushButton("캐시 경로 선택", self)
        cache_row.addWidget(self.cache_path_edit, 1)
        cache_row.addWidget(self.cache_choose)
        # Reproduce the previous implementation's non-widget reserved slot.
        cache_row.addSpacing(40)
        root.addLayout(cache_row)


class _SourceHost(QWidget):
    def __init__(self, saved_checked: bool, auction_checked: bool) -> None:
        super().__init__()
        self.livery_my_designs_toggle = QPushButton("내 디자인 리버리", self)
        self.livery_my_designs_toggle.setCheckable(True)
        self.livery_my_designs_toggle.setChecked(saved_checked)
        self.livery_auction_toggle = QPushButton("경매장 리버리", self)
        self.livery_auction_toggle.setCheckable(True)
        self.livery_auction_toggle.setChecked(auction_checked)
        self.persisted: list[tuple[str, bool]] = []

    def _fh6_v132_set_source_enabled(self, source: str, enabled: bool) -> None:
        self.persisted.append((source, bool(enabled)))


class UiFollowupV132Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv[:1])

    def test_path_rows_share_exact_button_columns(self) -> None:
        host = _PathHost()
        host.resize(1080, 120)
        host.show()
        self._app.processEvents()

        _align_path_rows(host)
        self._app.processEvents()
        self._app.processEvents()

        self.assertEqual(host.save_choose.width(), host.cache_choose.width())
        self.assertEqual(
            host.refresh.width(),
            host._fh6_v132_reserved_backup_slot.width(),
        )
        self.assertEqual(host.save_choose.geometry().x(), host.cache_choose.geometry().x())
        self.assertEqual(host.path_edit.geometry().right(), host.cache_path_edit.geometry().right())
        host.close()

    def test_legacy_both_on_normalizes_to_my_designs_and_stays_exclusive(self) -> None:
        host = _SourceHost(True, True)
        _configure_livery_source_switch(host)

        self.assertTrue(host.livery_my_designs_toggle.isChecked())
        self.assertFalse(host.livery_auction_toggle.isChecked())
        self.assertEqual(
            host.persisted,
            [("my_designs", True), ("auction", False)],
        )

        host.livery_auction_toggle.click()
        self.assertFalse(host.livery_my_designs_toggle.isChecked())
        self.assertTrue(host.livery_auction_toggle.isChecked())

        # An exclusive checked button cannot be toggled off by clicking it again.
        host.livery_auction_toggle.click()
        self.assertFalse(host.livery_my_designs_toggle.isChecked())
        self.assertTrue(host.livery_auction_toggle.isChecked())
        host.close()

    def test_valid_auction_only_legacy_state_is_preserved(self) -> None:
        host = _SourceHost(False, True)
        _configure_livery_source_switch(host)
        self.assertFalse(host.livery_my_designs_toggle.isChecked())
        self.assertTrue(host.livery_auction_toggle.isChecked())
        host.close()


if __name__ == "__main__":
    unittest.main()
