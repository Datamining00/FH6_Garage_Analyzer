from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from fh6garage.preview3d.tire_family_export import (
    TireFamilyExportError,
    export_tire_family_samples_from_directory,
)


def _write_tire(path: Path, left: bytes, right: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("tireL_sample.modelbin", left)
        archive.writestr("tireR_sample.modelbin", right)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TireFamilyExportTests(unittest.TestCase):
    def test_exports_unique_non_slick_geometry_read_only_and_builds_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tires = root / "game" / "tires"
            tires.mkdir(parents=True)
            slick = tires / "tire_Slick.zip"
            sport = tires / "tire_Sport.zip"
            street = tires / "tire_Street.zip"
            vintage = tires / "tire_Vintage.zip"
            _write_tire(slick, b"slick-left", b"slick-right")
            _write_tire(sport, b"sport-left", b"sport-right")
            _write_tire(street, b"street-left", b"street-right")
            _write_tire(vintage, b"sport-left", b"sport-right")
            before = {path: _sha256(path) for path in (slick, sport, street, vintage)}

            output = root / "diagnostics" / "families"
            report = export_tire_family_samples_from_directory(tires, output, limit=8)

            self.assertEqual(report.status, "diagnostic_tire_family_export_ready")
            self.assertFalse(report.production_mapping_enabled)
            self.assertTrue(report.source_archives_read_only_unchanged)
            self.assertEqual(report.exported_unique_geometry_count, 2)
            self.assertEqual([item.tire_model_name for item in report.exported], ["Sport", "Street"])
            self.assertEqual(len(report.skipped_duplicate_geometry), 1)
            self.assertEqual(report.skipped_duplicate_geometry[0].tire_model_name, "Vintage")
            self.assertEqual(report.skipped_duplicate_geometry[0].representative_tire_model_name, "Sport")
            self.assertTrue(Path(report.manifest_path).is_file())
            self.assertTrue(Path(report.bundle_path).is_file())

            manifest = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["exported_unique_geometry_count"], 2)
            self.assertFalse(manifest["production_mapping_enabled"])
            with zipfile.ZipFile(report.bundle_path, "r") as bundle:
                names = set(bundle.namelist())
            self.assertIn("native_tire_family_samples_manifest.json", names)
            self.assertIn("archives/tire_Sport.zip", names)
            self.assertIn("archives/tire_Street.zip", names)
            self.assertNotIn("archives/tire_Slick.zip", names)
            self.assertNotIn("archives/tire_Vintage.zip", names)

            for path, digest in before.items():
                self.assertEqual(_sha256(path), digest)
            for item in report.exported:
                self.assertTrue(item.copy_verified)
                self.assertEqual(item.source_archive_sha256, item.copied_archive_sha256)

    def test_output_inside_native_tire_library_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tires = Path(directory) / "tires"
            tires.mkdir()
            _write_tire(tires / "tire_Sport.zip", b"a", b"b")
            with self.assertRaisesRegex(TireFamilyExportError, "outside the native FH6 tire library"):
                export_tire_family_samples_from_directory(tires, tires / "export")

    def test_existing_output_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tires = root / "tires"
            output = root / "output"
            tires.mkdir()
            output.mkdir()
            _write_tire(tires / "tire_Sport.zip", b"a", b"b")
            with self.assertRaisesRegex(TireFamilyExportError, "already exists"):
                export_tire_family_samples_from_directory(tires, output)

    def test_nonpositive_limit_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tires = root / "tires"
            tires.mkdir()
            with self.assertRaisesRegex(TireFamilyExportError, "limit"):
                export_tire_family_samples_from_directory(tires, root / "output", limit=0)


if __name__ == "__main__":
    unittest.main()
