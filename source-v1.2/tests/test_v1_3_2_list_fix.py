from __future__ import annotations

import unittest
from pathlib import Path


class V132ListFixContractTests(unittest.TestCase):
    def test_app_installs_list_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_3_2_list_fixes(MainWindow)", source)

    def test_hidden_table_stays_my_designs_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_2_list_fix.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_fh6_v132_building_hidden_livery_table", source)
        self.assertIn("return list(self._custom_liveries())", source)

    def test_card_creation_is_not_replaced_or_batched(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_2_list_fix.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("_populate_livery_grid =", source)
        self.assertNotIn("QTimer", source)
        self.assertNotIn("batch", source.lower())


if __name__ == "__main__":
    unittest.main()
