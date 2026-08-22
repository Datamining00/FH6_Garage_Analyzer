from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fh6garage.v1_3_2_startup_patch import fast_auto_detect_thumbnail_cache


class V132StartupTests(unittest.TestCase):
    def test_verified_microsoft_path_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            cache = (
                local
                / "Packages"
                / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            cache.mkdir(parents=True)
            (cache / ".manifest").write_bytes(b"test")
            self.assertEqual(fast_auto_detect_thumbnail_cache(local), cache)

    def test_unrelated_microsoft_packages_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            packages = local / "Packages"
            packages.mkdir(parents=True)
            for index in range(500):
                decoy = packages / f"Microsoft.DecoyPackage{index}_8wekyb3d8bbwe"
                decoy.mkdir()
            self.assertIsNone(fast_auto_detect_thumbnail_cache(local))

    def test_known_alternate_package_family_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            cache = (
                local
                / "Packages"
                / "Microsoft.624F8B84B80_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            cache.mkdir(parents=True)
            (cache / ".manifest").write_bytes(b"test")
            self.assertEqual(fast_auto_detect_thumbnail_cache(local), cache)

    def test_app_installs_startup_patch(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_3_2_startup_patches()", source)


if __name__ == "__main__":
    unittest.main()
