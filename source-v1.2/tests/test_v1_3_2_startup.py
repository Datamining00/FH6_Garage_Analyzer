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
            # The directory intentionally does not exist. Returning it proves
            # startup does not probe for .manifest or search alternate paths.
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

    def test_app_installs_startup_patch(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_3_2_startup_patches()", source)

    def test_path_picker_row_is_replaced_by_hidden_holder(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_2_startup_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn("v132._install_cache_row = _install_fixed_cache_holder", source)
        self.assertIn("holder.setVisible(False)", source)


if __name__ == "__main__":
    unittest.main()
