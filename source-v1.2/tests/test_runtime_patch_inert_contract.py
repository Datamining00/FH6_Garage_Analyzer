from __future__ import annotations

import unittest
from pathlib import Path


class RuntimePatchInertContractTests(unittest.TestCase):
    INERT_PATCH_MODULES = (
        "v1_3_2_card_parent_patch",
        "v1_3_2_card_alignment_patch",
        "v1_3_2_diagnostic_patch",
        "v1_3_3_beta_identity_patch",
    )

    def test_legacy_patch_modules_exist_but_are_not_installed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "app.py").read_text(encoding="utf-8")
        package = root / "fh6garage"

        for module_name in self.INERT_PATCH_MODULES:
            with self.subTest(module=module_name):
                self.assertTrue((package / f"{module_name}.py").is_file())
                self.assertNotIn(module_name, app_source)

    def test_runtime_stack_keeps_explicit_stage_boundaries_and_finalizer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "app.py").read_text(encoding="utf-8")

        foundation = app_source.index("def _apply_foundation_patch_stack()")
        state = app_source.index("def _apply_state_patch_stack()")
        release = app_source.index("def _apply_release_patch_stack()")
        runtime = app_source.index("def _apply_runtime_patch_stack()")
        finalizer = app_source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)", runtime)

        self.assertLess(foundation, state)
        self.assertLess(state, release)
        self.assertLess(release, runtime)
        self.assertLess(runtime, finalizer)
        self.assertEqual(
            app_source.count("apply_v1_3_2_thread_affinity_fix(MainWindow)"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
