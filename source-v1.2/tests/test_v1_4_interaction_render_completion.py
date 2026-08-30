from __future__ import annotations

import unittest
from pathlib import Path


class V14InteractionRenderCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = Path(
            "fh6garage/v1_4_interaction_render_completion_patch.py"
        ).read_text(encoding="utf-8")

    def test_metadata_expansion_updates_viewport_first_then_chunks_rest(self):
        self.assertIn("_card_near_viewport(window, card)", self.text)
        self.assertIn("immediate.append(card)", self.text)
        self.assertIn("deferred.append(card)", self.text)
        self.assertIn("_METADATA_BACKGROUND_CHUNK = 32", self.text)
        self.assertIn("QTimer.singleShot(0, lambda next_start=end: apply_chunk(next_start))", self.text)
        start = self.text.index("def _set_metadata_collapsed_visible_first")
        body = self.text[start:self.text.index("def _finish_cached_layout_busy", start)]
        self.assertNotIn("for card in _features._registered_metadata_cards(window):", body)

    def test_backup_cached_layout_busy_finishes_after_visible_thumbnail_refresh(self):
        finish_start = self.text.index("def _finish_cached_layout_busy")
        finish_end = self.text.index("def _run_cached_layout_until_visible_paint", finish_start)
        finish = self.text[finish_start:finish_end]
        refresh = finish.index("_resilience._ORIGINAL_REFRESH_BACKUP_THUMBNAILS(window)")
        paint = finish.index("QApplication.processEvents(")
        end_busy = finish.index("end()")
        self.assertLess(refresh, paint)
        self.assertLess(paint, end_busy)

        run_start = self.text.index("def _run_cached_layout_until_visible_paint")
        run_end = self.text.index("def apply_v1_4_interaction_render_completion_patch", run_start)
        run = self.text[run_start:run_end]
        self.assertIn('window._fh6_backup_cached_layout_waiting = True', run)
        self.assertIn('if not bool(getattr(window, "_fh6_backup_relayout_active", False)):', run)
        self.assertNotIn("finally:\n        if scroll is not None", run)

    def test_backup_sort_keeps_existing_cache_and_lazy_offscreen_policy(self):
        lazy = Path("fh6garage/v1_3_4_backup_lazy_load_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("cards.sort(key=card_key)", lazy)
        self.assertIn("repository_read=0 card_create=0", lazy)
        self.assertIn("_backup_ui._relayout_backup(window)", lazy)
        self.assertIn("Off-screen thumbnails remain lazy", self.text)

    def test_source_label_click_copies_raw_acquisition_value(self):
        self.assertIn("class _AcquisitionCopyController(QObject):", self.text)
        self.assertIn("QApplication.clipboard().setText(self.copy_value)", self.text)
        self.assertIn("value = _acquisition._acquisition_text(info)", self.text)
        self.assertIn("Qt.CursorShape.PointingHandCursor", self.text)
        self.assertIn("클릭하여 출처 복사", self.text)
        self.assertNotIn('QApplication.clipboard().setText(f"출처:', self.text)

    def test_patch_order_is_after_acquisition_and_before_profiler(self):
        chain = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(
            encoding="utf-8"
        )
        acquisition = chain.rindex("apply_v1_4_acquisition_ui_patch(MainWindow)")
        vehicle_bridge = chain.rindex("apply_v1_4_vehicle_update_thread_bridge_patch(MainWindow)")
        interaction = chain.rindex("apply_v1_4_interaction_render_completion_patch(MainWindow)")
        profiler = chain.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(acquisition, interaction)
        self.assertLess(vehicle_bridge, interaction)
        self.assertLess(interaction, profiler)

        app = Path("app.py").read_text(encoding="utf-8")
        wording = app.rindex("apply_v1_3_4_backup_action_wording_patch(MainWindow)")
        affinity = app.rindex("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(wording, affinity)


if __name__ == "__main__":
    unittest.main()
