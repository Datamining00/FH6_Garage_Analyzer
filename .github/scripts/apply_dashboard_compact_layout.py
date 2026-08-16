from __future__ import annotations

from pathlib import Path

ROOT = Path("source-v1.2")
UI = ROOT / "fh6garage" / "ui.py"
TEST = ROOT / "tests" / "test_dashboard_compact_layout.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label} fragment not found")
    return text.replace(old, new, 1)


source = UI.read_text(encoding="utf-8")

source = replace_once(
    source,
    '''        left = QFrame(); left.setObjectName("panel")
        left_l = QVBoxLayout(left); left_l.setContentsMargins(14, 14, 14, 14)
        row = QHBoxLayout()
''',
    '''        left = QFrame(); left.setObjectName("panel")
        left_l = QVBoxLayout(left); left_l.setContentsMargins(14, 14, 14, 14)
        dashboard_controls = QGridLayout()
        dashboard_controls.setHorizontalSpacing(7)
        dashboard_controls.setVerticalSpacing(7)
''',
    "dashboard controls layout",
)

source = replace_once(
    source,
    '''        self.car_search = QLineEdit()
        self.car_search.setPlaceholderText(tr("dashboard.search_vehicle"))
        self.car_search.setFixedWidth(260)
        self._connect_debounced_search(
            self.car_search,
            self._filter_dashboard_table,
        )

        row.addWidget(self.dashboard_car_button)
        row.addWidget(self.dashboard_creator_button)
        row.addStretch(1)
        row.addWidget(self.car_search)
        left_l.addLayout(row)
''',
    '''        self.car_search = QLineEdit()
        self.car_search.setPlaceholderText(tr("dashboard.search_vehicle"))
        self.car_search.setMinimumWidth(0)
        self.car_search.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._connect_debounced_search(
            self.car_search,
            self._filter_dashboard_table,
        )

        # Keep the mode selectors on their own compact row and let the search
        # field use the full panel width below. This avoids English text forcing
        # the minimum window wider than the declared 960 px compact layout.
        dashboard_controls.addWidget(self.dashboard_car_button, 0, 0)
        dashboard_controls.addWidget(self.dashboard_creator_button, 0, 1)
        dashboard_controls.setColumnStretch(2, 1)
        dashboard_controls.addWidget(self.car_search, 1, 0, 1, 3)
        left_l.addLayout(dashboard_controls)
''',
    "dashboard controls widgets",
)

source = replace_once(
    source,
    '''        right = QFrame(); right.setObjectName("panel")
        right_l = QVBoxLayout(right); right_l.setContentsMargins(14, 14, 14, 14)
''',
    '''        right = QFrame(); right.setObjectName("panel")
        # The detail tables need enough horizontal room for Livery/Creator and
        # Name/Creator/Size headers even at the 960 px minimum window width.
        right.setMinimumWidth(280)
        right_l = QVBoxLayout(right); right_l.setContentsMargins(14, 14, 14, 14)
''',
    "dashboard right panel minimum width",
)

UI.write_text(source, encoding="utf-8")

TEST.write_text(
    '''from pathlib import Path\nimport unittest\n\n\nROOT = Path(__file__).resolve().parents[1]\nUI_SOURCE = ROOT / "fh6garage" / "ui.py"\n\n\nclass DashboardCompactLayoutTests(unittest.TestCase):\n    def test_dashboard_search_is_responsive(self):\n        source = UI_SOURCE.read_text(encoding="utf-8")\n        self.assertIn("dashboard_controls = QGridLayout()", source)\n        self.assertIn("dashboard_controls.addWidget(self.car_search, 1, 0, 1, 3)", source)\n        self.assertIn("self.car_search.setMinimumWidth(0)", source)\n        self.assertNotIn("self.car_search.setFixedWidth(260)", source)\n\n    def test_dashboard_detail_panel_keeps_compact_minimum_width(self):\n        source = UI_SOURCE.read_text(encoding="utf-8")\n        self.assertIn("right.setMinimumWidth(280)", source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("Dashboard compact layout patch prepared")
