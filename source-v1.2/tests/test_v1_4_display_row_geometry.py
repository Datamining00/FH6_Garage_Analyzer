from __future__ import annotations

import unittest
from pathlib import Path


class V14DisplayRowGeometryTests(unittest.TestCase):
    def test_recent_counts_have_intrinsic_width_before_first_paint(self):
        text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")
        self.assertIn("return max(96, calculated, view.sizeHint().width())", text)
        self.assertIn("view.setMinimumWidth(intrinsic)", text)
        self.assertIn("banner.setMinimumWidth(intrinsic)", text)
        self.assertIn("widget.setMinimumWidth(widget.sizeHint().width())", text)

    def test_geometry_uses_real_widget_lifecycle_not_new_timer_band_aid(self):
        text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")
        self.assertIn("def patched_show_event", text)
        self.assertIn("def patched_resize_event", text)
        self.assertIn("_sync_display_row_geometry(self)", text)
        self.assertNotIn("QTimer", text)
        self.assertNotIn("singleShot", text)

    def test_safe_sync_replaces_old_banner_width_callback(self):
        text = Path("fh6garage/v1_4_display_row_geometry_patch.py").read_text(encoding="utf-8")
        self.assertIn("_ui._sync_recent_change_banner_width = _sync_display_row_geometry", text)
        self.assertIn("export_right - banner_left", text)
        self.assertIn("banner.setFixedWidth(target)", text)

    def test_patch_order_is_after_ui_completion_before_profiler(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        ui = text.rindex("apply_v1_4_ui_completion_patch(MainWindow)")
        geometry = text.rindex("apply_v1_4_display_row_geometry_patch(MainWindow)")
        profiler = text.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(ui, geometry)
        self.assertLess(geometry, profiler)


if __name__ == "__main__":
    unittest.main()
