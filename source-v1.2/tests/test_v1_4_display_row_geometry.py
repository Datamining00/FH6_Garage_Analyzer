from __future__ import annotations

import unittest
from pathlib import Path


class V14DisplayRowGeometryTests(unittest.TestCase):
    def test_recent_counts_and_export_share_structural_right_anchor(self):
        text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")
        self.assertIn("def _pin_widget_after_trailing_stretch", text)
        self.assertIn("_pin_widget_after_trailing_stretch(display_row, banner)", text)
        self.assertIn("_pin_widget_after_trailing_stretch(action_row, export)", text)
        self.assertIn('getattr(window, "_saved_content_action_rows", {}).get("livery")', text)
        self.assertIn("layout.removeWidget(widget)", text)
        self.assertIn("layout.addWidget(widget)", text)
        self.assertNotIn("export_right - banner_left", text)
        self.assertNotIn("mapTo(", text)

    def test_counter_width_is_content_stable_not_right_edge_driver(self):
        text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")
        self.assertIn("intrinsic = _intrinsic_recent_width(window)", text)
        self.assertIn("banner.setFixedWidth(intrinsic)", text)
        self.assertIn("view.setFixedWidth(intrinsic)", text)
        self.assertIn("QSizePolicy.Policy.Fixed", text)
        self.assertIn("widget.setMinimumWidth(widget.sizeHint().width())", text)

    def test_geometry_uses_widget_lifecycle_without_timer_or_coordinate_observer(self):
        text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")
        self.assertIn("def patched_show_event", text)
        self.assertIn("def patched_resize_event", text)
        self.assertNotIn("QTimer", text)
        self.assertNotIn("singleShot", text)
        self.assertNotIn("_RightEdgeObserver", text)
        self.assertNotIn("QEvent.Type.Move", text)

    def test_safe_sync_replaces_old_banner_width_callback(self):
        text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")
        self.assertIn("_ui._sync_recent_change_banner_width = _sync_display_row_geometry", text)
        self.assertIn("structural right anchor", text)

    def test_patch_order_is_after_ui_completion_before_profiler(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        ui = text.rindex("apply_v1_4_ui_completion_patch(MainWindow)")
        geometry = text.rindex("apply_v1_4_display_row_geometry_patch(MainWindow)")
        profiler = text.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(ui, geometry)
        self.assertLess(geometry, profiler)


if __name__ == "__main__":
    unittest.main()
