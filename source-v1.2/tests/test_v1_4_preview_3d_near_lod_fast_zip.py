from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from fh6garage.preview3d.near_lod import _copy_archive_with_sha256, _rewrite_copied_zip_entries


class Preview3DNearLodFastZipTests(unittest.TestCase):
    def test_selective_rewrite_preserves_source_and_unmodified_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "vehicle.zip"
            derived = root / "derived.zip"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("Scene/car.carbin", b"carbin-original")
                archive.writestr("Scene/body.modelbin", b"body-original" * 200)
                archive.writestr("Scene/keep.bin", b"keep-me" * 500)
                archive.writestr("Scene/body__slod.modelbin", b"slod-original" * 200)

            source_before = source.read_bytes()
            source_sha = hashlib.sha256(source_before).hexdigest()
            copied_sha = _copy_archive_with_sha256(source, derived)
            self.assertEqual(copied_sha, source_sha)
            self.assertEqual(derived.read_bytes(), source_before)

            _rewrite_copied_zip_entries(
                derived,
                {
                    "Scene/body.modelbin": ("Scene/body.modelbin", b"body-patched"),
                    "Scene/body__slod.modelbin": ("Scene/body__NLOD.modelbin", b"slod-patched"),
                },
            )

            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_sha)
            with zipfile.ZipFile(derived, "r") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(
                    archive.namelist(),
                    [
                        "Scene/car.carbin",
                        "Scene/body.modelbin",
                        "Scene/keep.bin",
                        "Scene/body__NLOD.modelbin",
                    ],
                )
                self.assertEqual(archive.read("Scene/car.carbin"), b"carbin-original")
                self.assertEqual(archive.read("Scene/body.modelbin"), b"body-patched")
                self.assertEqual(archive.read("Scene/keep.bin"), b"keep-me" * 500)
                self.assertEqual(archive.read("Scene/body__NLOD.modelbin"), b"slod-patched")
                self.assertNotIn("Scene/body__slod.modelbin", archive.namelist())

    def test_selective_rewrite_rejects_output_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "vehicle.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("a.bin", b"a")
                archive.writestr("b.bin", b"b")

            with self.assertRaisesRegex(Exception, "collides"):
                _rewrite_copied_zip_entries(
                    archive_path,
                    {"a.bin": ("b.bin", b"replacement")},
                )


if __name__ == "__main__":
    unittest.main()
