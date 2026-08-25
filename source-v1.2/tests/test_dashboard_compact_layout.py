from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SOURCE = ROOT / "fh6garage" / "dashboard_page_builder.py"


class DashboardCompactLayoutTests(unittest.TestCase):
    def test_dashboard_search_is_responsive(self):
        source = DASHBOARD_SOURCE.read_text(encoding="utf-8")
        self.assertIn("controls = QGridLayout()", source)
        self.assertIn("controls.addWidget(owner.car_search, 1, 0, 1, 3)", source)
        self.assertIn("owner.car_search.setMinimumWidth(0)", source)
        self.assertNotIn("owner.car_search.setFixedWidth(260)", source)

    def test_dashboard_detail_panel_keeps_compact_minimum_width(self):
        source = DASHBOARD_SOURCE.read_text(encoding="utf-8")
        self.assertIn("panel.setMinimumWidth(280)", source)


if __name__ == "__main__":
    unittest.main()
