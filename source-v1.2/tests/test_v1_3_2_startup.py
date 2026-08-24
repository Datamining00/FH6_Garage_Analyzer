from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fh6garage.v1_3_2_startup_patch import fixed_default_thumbnail_cache


class V132StartupTests(unittest.TestCase):
    def test_default_path_is_fixed_without_filesystem_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            expected = (
                local
                / "Packages"
                / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            self.assertEqual(fixed_default_thumbnail_cache(local), expected)

    def test_steam_and_alternate_packages_are_not_considered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            steam = local / "ForzaHorizon6" / "LocalStorage_Cache" / "CacheThumbnails"
            alternate = (
                local
                / "Packages"
                / "Microsoft.624F8B84B80_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            steam.mkdir(parents=True)
            alternate.mkdir(parents=True)
            expected = (
                local
                / "Packages"
                / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            self.assertEqual(fixed_default_thumbnail_cache(local), expected)

    def test_app_uses_startup_patch_with_diagnostic_instrumentation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_3_2_startup_patches()", source)
        self.assertIn("apply_v1_3_2_performance_patches(MainWindow)", source)
        self.assertTrue(
            (root / "fh6garage" / "v1_3_2_performance_patch.py").exists()
        )
        self.assertLess(
            source.index("apply_v1_3_2_performance_patches(MainWindow)"),
            source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)"),
        )

    def test_manual_picker_remains_but_auto_discovery_button_is_removed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_2_startup_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn("v132._install_cache_row = _install_fixed_cache_row", source)
        self.assertIn("choose.setObjectName(\"primary\")", source)
        self.assertIn("refresh.setObjectName(\"secondary\")", source)
        self.assertNotIn("Microsoft.*", source)
        self.assertNotIn("os.scandir", source)


if __name__ == "__main__":
    unittest.main()
