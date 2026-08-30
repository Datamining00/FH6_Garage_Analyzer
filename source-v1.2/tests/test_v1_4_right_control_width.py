from __future__ import annotations

import unittest
from pathlib import Path


class V14RightControlWidthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = Path("fh6garage/v1_4_right_control_width_patch.py").read_text(encoding="utf-8")

    def test_export_size_hint_is_the_single_reference_width(self):
        self.assertIn('getattr(window, "livery_export_visible_button", None)', self.text)
        self.assertIn('return max(1, int(export.sizeHint().width()))', self.text)
        self.assertIn('window._fh6_right_control_reference_width = width', self.text)

    def test_livery_tuning_backup_right_controls_share_reference_width(self):
        for name in (
            'livery_check_filter',
            'livery_export_visible_button',
            'tuning_check_filter',
            'backup_refresh_button',
            'backup_filter_button',
        ):
            self.assertIn(f'getattr(window, "{name}", None)', self.text)
        self.assertIn('_global_refresh_button(window)', self.text)
        self.assertIn('tr("save.refresh")', self.text)
        self.assertIn('widget.setFixedWidth(width)', self.text)

    def test_recent_counter_outer_and_inner_width_match_export(self):
        self.assertIn('getattr(window, "refresh_diff_banner", None)', self.text)
        self.assertIn('getattr(window, "refresh_diff_view_button", None)', self.text)
        self.assertIn('banner.setFixedWidth(width)', self.text)
        self.assertIn('_set_fixed_control_width(counter, width)', self.text)

    def test_deferred_ui_completion_cannot_restore_intrinsic_counter_width(self):
        self.assertIn('def _sync_right_geometry_and_widths', self.text)
        combined = self.text[self.text.index('def _sync_right_geometry_and_widths'):]
        self.assertLess(
            combined.index('_geometry._sync_display_row_geometry(window)'),
            combined.index('_sync_right_control_widths(window)'),
        )
        self.assertIn(
            '_ui._sync_recent_change_banner_width = _sync_right_geometry_and_widths',
            self.text,
        )

    def test_patch_reasserts_width_after_existing_geometry_lifecycle(self):
        self.assertIn('def patched_show_event', self.text)
        self.assertIn('def patched_resize_event', self.text)
        self.assertIn('_sync_right_geometry_and_widths(self)', self.text)
        chain = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        geometry = chain.rindex('apply_v1_4_display_row_geometry_patch(MainWindow)')
        right_width = chain.rindex('apply_v1_4_right_control_width_patch(MainWindow)')
        profiler = chain.rindex('apply_v1_3_4_performance_probe_patch(MainWindow)')
        self.assertLess(geometry, right_width)
        self.assertLess(right_width, profiler)


if __name__ == "__main__":
    unittest.main()
