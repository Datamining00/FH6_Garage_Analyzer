from __future__ import annotations

import ast
import unittest
from pathlib import Path


def _sequence_entries(source: str) -> list[tuple[str, bool]]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "RUNTIME_PATCH_SEQUENCE" or not isinstance(node.value, ast.Tuple):
            continue
        entries: list[tuple[str, bool]] = []
        for item in node.value.elts:
            if not isinstance(item, ast.Call) or len(item.args) < 3:
                raise AssertionError("Invalid RuntimePatchStep entry")
            name_node, _callable_node, main_window_node = item.args[:3]
            if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
                raise AssertionError("RuntimePatchStep name must be a string literal")
            if not isinstance(main_window_node, ast.Constant) or not isinstance(main_window_node.value, bool):
                raise AssertionError("uses_main_window must be a bool literal")
            entries.append((name_node.value, main_window_node.value))
        return entries
    raise AssertionError("RUNTIME_PATCH_SEQUENCE not found")


class RuntimeCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.composition = (
            self.root / "fh6garage" / "runtime_composition.py"
        ).read_text(encoding="utf-8")
        self.entries = _sequence_entries(self.composition)
        self.names = [name for name, _uses_main_window in self.entries]

    def test_registry_is_explicit_unique_and_preserves_legacy_step_count(self) -> None:
        self.assertEqual(len(self.entries), 65)
        self.assertEqual(len(set(self.names)), 65)
        startup = dict(self.entries)["v1_3_2_startup"]
        self.assertFalse(startup)

    def test_final_thread_affinity_contract_is_explicit(self) -> None:
        self.assertEqual(self.names[-1], "v1_3_2_thread_affinity_fix")
        self.assertIn('names[-1] != "v1_3_2_thread_affinity_fix"', self.composition)

    def test_former_hidden_backup_tail_is_now_explicit(self) -> None:
        wording = self.names.index("v1_3_4_backup_action_wording")
        hidden_first = self.names.index("v1_3_4_backup_import_refinement")
        hidden_last = self.names.index("v1_3_4_performance_probe")
        affinity = self.names.index("v1_3_2_thread_affinity_fix")
        self.assertEqual(hidden_first, wording + 1)
        self.assertLess(hidden_first, hidden_last)
        self.assertEqual(affinity, hidden_last + 1)

    def test_app_uses_only_the_composition_root(self) -> None:
        app = (self.root / "app.py").read_text(encoding="utf-8")
        self.assertIn(
            "from fh6garage.runtime_composition import apply_runtime_patches",
            app,
        )
        self.assertIn("apply_runtime_patches(MainWindow)", app)
        self.assertNotIn("apply_v1_3_4_backup_action_wording_patch(MainWindow)", app)
        self.assertNotIn("apply_v1_3_2_thread_affinity_fix(MainWindow)", app)


if __name__ == "__main__":
    unittest.main()
