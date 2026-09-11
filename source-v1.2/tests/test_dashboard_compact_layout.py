from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = ROOT / "fh6garage" / "ui.py"


class DashboardCompactLayoutTests(unittest.TestCase):
    def test_dashboard_search_is_responsive(self):
        source = UI_SOURCE.read_text(encoding="utf-8")
        self.assertIn("dashboard_controls = QGridLayout()", source)
        self.assertIn("dashboard_controls.addWidget(self.car_search, 1, 0, 1, 3)", source)
        self.assertIn("self.car_search.setMinimumWidth(0)", source)
        self.assertNotIn("self.car_search.setFixedWidth(260)", source)

    def test_dashboard_detail_panel_keeps_compact_minimum_width(self):
        source = UI_SOURCE.read_text(encoding="utf-8")
        self.assertIn("right.setMinimumWidth(280)", source)


if __name__ == "__main__":
    unittest.main()
