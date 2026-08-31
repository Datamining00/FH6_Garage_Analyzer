from __future__ import annotations

import ast
import unittest
from pathlib import Path


def _runtime_patch_names(root: Path) -> list[str]:
    source = (root / "fh6garage" / "runtime_composition.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id != "RUNTIME_PATCH_SEQUENCE" or not isinstance(node.value, ast.Tuple):
                continue
            names: list[str] = []
            for item in node.value.elts:
                if not isinstance(item, ast.Call) or not item.args:
                    continue
                first = item.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.append(first.value)
            return names
    raise AssertionError("RUNTIME_PATCH_SEQUENCE not found")


class BackupActionWordingTests(unittest.TestCase):
    def test_backup_tab_uses_backup_wording(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"백업하기"', source)
        self.assertIn("게임 쪽 원본", source)
        self.assertNotIn("delete.setEnabled(False)", source)
        self.assertIn("_fh6_export_delete_source_requested", source)
        self.assertIn("폴더 지문", source)

    def test_wording_patch_stays_before_final_thread_affinity_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        names = _runtime_patch_names(root)
        performance = names.index("v1_3_4_backup_export_performance_ui")
        wording = names.index("v1_3_4_backup_action_wording")
        affinity = names.index("v1_3_2_thread_affinity_fix")
        self.assertLess(performance, wording)
        self.assertLess(wording, affinity)

    def test_wording_patch_no_longer_installs_unrelated_followups(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_4_backup_import_refinement_patch", source)
        self.assertNotIn("apply_v1_4_identity_patch", source)
        self.assertIn("runtime_composition", source)


if __name__ == "__main__":
    unittest.main()
