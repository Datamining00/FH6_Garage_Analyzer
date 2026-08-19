from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _Record:
    key: str
    content_sha256: str = ""
    livery_path: object | None = None


class LiveryListRebuildPerformancePatchTests(unittest.TestCase):
    def test_app_wires_rebuild_fix_after_startup_patch(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_livery_startup_performance_patch(MainWindow)", source)
        self.assertIn("apply_livery_list_rebuild_performance_patch(MainWindow)", source)
        self.assertLess(
            source.index("apply_livery_startup_performance_patch(MainWindow)"),
            source.index("apply_livery_list_rebuild_performance_patch(MainWindow)"),
        )

    def test_large_grid_is_built_incrementally_and_yields_to_ui(self) -> None:
        source = (
            ROOT / "fh6garage" / "livery_list_rebuild_performance_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_FIRST_BATCH = 8", source)
        self.assertIn("_INCREMENTAL_BATCH = 8", source)
        self.assertIn("_INCREMENTAL_DELAY_MS = 4", source)
        self.assertIn("_fh6_livery_grid_generation", source)
        self.assertIn("_BATCH_BUDGET_MS", source)
        self.assertIn('"livery_list_first_paint"', source)
        self.assertIn('"livery_list_rebuild_complete"', source)
        self.assertNotIn("_populate_saved_content_table(\"livery\")", source)

    def test_thumbnail_decode_is_one_at_a_time(self) -> None:
        source = (
            ROOT / "fh6garage" / "livery_list_rebuild_performance_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_THUMBNAIL_BATCH = 1", source)
        self.assertIn("_queue_thumbnail_load", source)
        self.assertIn("_drain_thumbnail_queue", source)
        self.assertIn("thumbnail_decode_batch", source)

    def test_lookup_and_duplicate_caches_are_not_quadratic(self) -> None:
        import fh6garage.livery_list_rebuild_performance_patch as patch

        patch._APPLIED = False

        class DummyWindow:
            def __init__(self):
                self.result = object()
                self.livery_grid_host = object()
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
                pass

            def _load_livery_card_thumbnail(self, card):
                pass

            def _unload_livery_card_thumbnail(self, card):
                pass

            def _saved_content_records(self, content_type):
                return self.liveries if content_type == "livery" else self.tunings

            def _content_annotation_key(self, content_type, record):
                return f"{content_type}:{record.key}"

            def _custom_liveries(self):
                return self.liveries

        patch.apply_livery_list_rebuild_performance_patch(DummyWindow)
        window = DummyWindow()

        self.assertIs(
            window._record_for_content_key("livery", "livery:b"),
            window.liveries[1],
        )
        self.assertEqual(window._duplicate_livery_hashes(), {"same"})

        window.liveries[2].content_sha256 = "same"
        self.assertEqual(window._duplicate_livery_hashes(), {"same"})
        window._invalidate_livery_lookup_caches()
        self.assertEqual(window._duplicate_livery_hashes(), {"same"})

        window._apply_pointing_cursors(window.livery_grid_host)
        self.assertEqual(window.cursor_calls, 0)
        window._apply_pointing_cursors(object())
        self.assertEqual(window.cursor_calls, 1)


if __name__ == "__main__":
    unittest.main()
