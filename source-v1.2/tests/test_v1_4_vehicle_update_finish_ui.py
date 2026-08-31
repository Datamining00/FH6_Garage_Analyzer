from __future__ import annotations

import unittest
from pathlib import Path


class V14VehicleUpdateFinishUITests(unittest.TestCase):
    def test_update_dialog_uses_requested_labels(self):
        text = Path("fh6garage/v1_4_vehicle_update_finish_ui_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('box.addButton("HDR 데이터"', text)
        self.assertIn('box.addButton("차량 데이터2"', text)
        self.assertIn('box.addButton("취소"', text)
        self.assertNotIn('box.addButton("내 차량 데이터"', text)

    def test_hdr_disables_supplemental_data_but_vehicle_data2_keeps_it(self):
        text = Path("fh6garage/v1_4_vehicle_update_finish_ui_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def _disable_supplemental_cache", text)
        self.assertIn('SUPPLEMENTAL_DISABLED_KEY: True', text)
        self.assertIn('"source": _vehicle_source.HDR_SOURCE', text)
        self.assertIn("if source == _vehicle_source.HDR_SOURCE:", text)
        self.assertIn("_disable_supplemental_cache(self.acquisition_db)", text)
        self.assertIn("self.acquisition_db.reload()", text)
        self.assertNotIn("if source == _vehicle_source.USER_SOURCE:\n                _disable_supplemental_cache", text)

    def test_success_finishes_update_without_full_save_rescan(self):
        text = Path("fh6garage/v1_4_vehicle_update_finish_ui_patch.py").read_text(
            encoding="utf-8"
        )
        start = text.index("def update_finished")
        body = text[start:]
        self.assertIn("self._end_busy()", body)
        self.assertIn("self.db_update_button.setEnabled(True)", body)
        self.assertIn('self.db_update_button.setText(tr("db.check_update"))', body)
        self.assertIn('populate = getattr(self, "_populate_all", None)', body)
        self.assertNotIn("self.start_scan(", body)

    def test_added_change_card_uses_fixed_main_card_width(self):
        text = Path("fh6garage/v1_4_vehicle_update_finish_ui_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("card.setFixedWidth(card_width)", text)
        self.assertIn(
            "card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)",
            text,
        )
        self.assertIn('card.findChild(QLabel, "fh6AcquisitionPlaceholder")', text)
        self.assertIn("layout.activate()", text)

    def test_completion_patch_is_after_vehicle_source_before_profiler(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(
            encoding="utf-8"
        )
        vehicle = text.rindex("apply_v1_4_vehicle_data_source_patch(MainWindow)")
        finish = text.rindex("apply_v1_4_vehicle_update_finish_ui_patch(MainWindow)")
        profiler = text.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(vehicle, finish)
        self.assertLess(finish, profiler)

        app = Path("app.py").read_text(encoding="utf-8")
        wording = app.rindex("apply_v1_3_4_backup_action_wording_patch(MainWindow)")
        affinity = app.rindex("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(wording, affinity)


if __name__ == "__main__":
    unittest.main()
