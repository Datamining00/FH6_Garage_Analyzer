from __future__ import annotations

import unittest
from pathlib import Path


class V14DisplayRowGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")

    def test_recent_counts_and_export_share_structural_right_anchor(self):
        self.assertIn("def _pin_pair_after_trailing_stretch", self.text)
        self.assertIn("def _pin_widget_after_trailing_stretch", self.text)
        self.assertIn("_pin_pair_after_trailing_stretch(display_row, no_applied, banner)", self.text)
        self.assertIn("_pin_widget_after_trailing_stretch(action_row, export)", self.text)
        self.assertIn('getattr(window, "_saved_content_action_rows", {}).get("livery")', self.text)
        self.assertIn("layout.removeWidget(left_widget)", self.text)
        self.assertIn("layout.addWidget(right_widget)", self.text)
        self.assertNotIn("export_right - banner_left", self.text)
        self.assertNotIn("mapTo(", self.text)

    def test_recent_counter_has_no_independent_width_policy(self):
        self.assertNotIn("_intrinsic_recent_width", self.text)
        self.assertNotIn("banner.setFixedWidth", self.text)
        self.assertNotIn("view.setFixedWidth", self.text)
        self.assertIn("width is owned by the shared-width patch", self.text)

    def test_search_and_no_applied_use_same_terminal_gap_geometry(self):
        self.assertIn("_RIGHT_COLUMN_GAP = 7", self.text)
        self.assertIn("search_row.setSpacing(_RIGHT_COLUMN_GAP)", self.text)
        self.assertIn("display_row.setSpacing(_RIGHT_COLUMN_GAP)", self.text)
        self.assertIn("action_row.setSpacing(_RIGHT_COLUMN_GAP)", self.text)
        self.assertIn('getattr(window, "livery_no_applied_toggle", None)', self.text)

    def test_geometry_uses_widget_lifecycle_without_timer_or_coordinate_observer(self):
        self.assertIn("def patched_show_event", self.text)
        self.assertIn("def patched_resize_event", self.text)
        self.assertNotIn("QTimer", self.text)
        self.assertNotIn("singleShot", self.text)
        self.assertNotIn("_RightEdgeObserver", self.text)
        self.assertNotIn("QEvent.Type.Move", self.text)

    def test_safe_sync_replaces_old_banner_width_callback(self):
        self.assertIn("_ui._sync_recent_change_banner_width = _sync_display_row_geometry", self.text)
        self.assertIn("re-assert structure only", self.text)

    def test_patch_order_is_after_ui_completion_before_shared_width_and_profiler(self):
        chain = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        ui = chain.rindex("apply_v1_4_ui_completion_patch(MainWindow)")
        geometry = chain.rindex("apply_v1_4_display_row_geometry_patch(MainWindow)")
        right_width = chain.rindex("apply_v1_4_right_control_width_patch(MainWindow)")
        profiler = chain.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(ui, geometry)
        self.assertLess(geometry, right_width)
        self.assertLess(right_width, profiler)


if __name__ == "__main__":
    unittest.main()
