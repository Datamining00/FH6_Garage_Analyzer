from __future__ import annotations

import unittest
from pathlib import Path


class V14VehicleUpdateThreadBridgeTests(unittest.TestCase):
    def test_worker_results_are_queued_to_real_qobject_bridge(self):
        text = Path("fh6garage/v1_4_vehicle_update_thread_bridge_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class _VehicleUpdateGuiBridge(QObject):", text)
        self.assertIn("@Slot(object)\n    def update_finished", text)
        self.assertIn("@Slot(str)\n    def update_failed", text)
        self.assertIn("bridge = _VehicleUpdateGuiBridge(self)", text)
        self.assertIn("bridge.update_finished,\n            Qt.ConnectionType.QueuedConnection", text)
        self.assertIn("bridge.update_failed,\n            Qt.ConnectionType.QueuedConnection", text)
        self.assertNotIn("worker.finished.connect(self._car_db_update_finished)", text)
        self.assertNotIn("worker.failed.connect(self._car_db_update_failed)", text)

    def test_worker_thread_quit_is_not_blocked_by_gui_callback(self):
        text = Path("fh6garage/v1_4_vehicle_update_thread_bridge_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)",
            text,
        )
        self.assertIn(
            "worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)",
            text,
        )
        quit_pos = text.index("worker.finished.connect(thread.quit")
        gui_pos = text.index("bridge.update_finished")
        self.assertLess(quit_pos, gui_pos)

    def test_bridge_records_gui_thread_affinity(self):
        text = Path("fh6garage/v1_4_vehicle_update_thread_bridge_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QThread.currentThread() is window.thread()", text)
        self.assertIn("_fh6_vehicle_update_callback_on_gui_thread", text)

    def test_bridge_patch_order_preserves_final_affinity_patch(self):
        chain = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(
            encoding="utf-8"
        )
        finish = chain.rindex("apply_v1_4_vehicle_update_finish_ui_patch(MainWindow)")
        bridge = chain.rindex("apply_v1_4_vehicle_update_thread_bridge_patch(MainWindow)")
        profiler = chain.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(finish, bridge)
        self.assertLess(bridge, profiler)

        app = Path("app.py").read_text(encoding="utf-8")
        wording = app.rindex("apply_v1_3_4_backup_action_wording_patch(MainWindow)")
        affinity = app.rindex("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(wording, affinity)


if __name__ == "__main__":
    unittest.main()
