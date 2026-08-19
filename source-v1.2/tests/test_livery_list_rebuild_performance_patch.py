from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _Record:
    key: str
    content_sha256: str = ""


class _Table:
    def __init__(self, rows: int = 5):
        self.rows = rows

    def rowCount(self):
        return self.rows

    def setRowCount(self, value):
        self.rows = int(value)


class LiveryListRebuildPerformancePatchTests(unittest.TestCase):
    def test_app_wires_rebuild_fix_after_startup_patch(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_livery_startup_performance_patch(MainWindow)", source)
        self.assertIn("apply_livery_list_rebuild_performance_patch(MainWindow)", source)
        self.assertLess(
            source.index("apply_livery_startup_performance_patch(MainWindow)"),
            source.index("apply_livery_list_rebuild_performance_patch(MainWindow)"),
        )

    def test_patch_removes_hidden_table_and_quadratic_lookup_work(self) -> None:
        import fh6garage.livery_list_rebuild_performance_patch as patch

        patch._APPLIED = False

        class DummyWindow:
            def __init__(self):
                self.result = object()
                self.livery_table = _Table(7)
                self.livery_grid_host = object()
                self._livery_grid_cards = []
                self.grid_builds = 0
                self.cursor_calls = 0
                self.liveries = [
                    _Record("a", "same"),
                    _Record("b", "same"),
                    _Record("c", "unique"),
                ]
                self.tunings = [_Record("t")]

            def _scan_finished(self, result):
                self.result = result

            def _apply_pointing_cursors(self, root):
                self.cursor_calls += 1

            def _populate_livery_grid(self):
                self.grid_builds += 1
                self._livery_grid_cards = [object()] * len(self.liveries)

            def _saved_content_records(self, content_type):
                return self.liveries if content_type == "livery" else self.tunings

            def _content_annotation_key(self, content_type, record):
                return f"{content_type}:{record.key}"

            def _custom_liveries(self):
                return self.liveries

        patch.apply_livery_list_rebuild_performance_patch(DummyWindow)
        window = DummyWindow()

        window._populate_livery_table()
        self.assertEqual(window.livery_table.rowCount(), 0)
        self.assertEqual(window.grid_builds, 1)
        self.assertIs(window._record_for_content_key("livery", "livery:b"), window.liveries[1])
        self.assertEqual(window._duplicate_livery_hashes(), {"same"})

        # Cached duplicate membership remains stable until explicitly invalidated.
        window.liveries[2].content_sha256 = "same"
        self.assertEqual(window._duplicate_livery_hashes(), {"same"})
        window._invalidate_livery_lookup_caches()
        self.assertEqual(window._duplicate_livery_hashes(), {"same"})

        # Whole-host cursor traversal is skipped; per-card traversal still works.
        window._apply_pointing_cursors(window.livery_grid_host)
        self.assertEqual(window.cursor_calls, 0)
        window._apply_pointing_cursors(object())
        self.assertEqual(window.cursor_calls, 1)


if __name__ == "__main__":
    unittest.main()
