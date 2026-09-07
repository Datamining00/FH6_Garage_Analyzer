from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from fh6garage.preview3d.tire_cross_family_diagnostic import (
    TireCrossFamilyDiagnosticError,
    run_native_tire_cross_family_diagnostic_from_directory,
)
from tests.test_tire_morph_geometry import _bundle


def _write_tire(path: Path, entry: str, modelbin: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry, modelbin)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TireCrossFamilyDiagnosticTests(unittest.TestCase):
    def test_one_click_exports_compares_and_bundles_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tires = root / "tires"
            tires.mkdir()
            slick = tires / "tire_slick.zip"
            sport = tires / "tire_sport.zip"
            base = _bundle()
            distinct_container_geometry = bytearray(base)
            distinct_container_geometry[8] = 1  # ignored Bundle header byte; keeps parsed selector geometry identical
            _write_tire(slick, "tireL_slick.modelbin", base)
            _write_tire(sport, "tireL_sport.modelbin", bytes(distinct_container_geometry))
            slick_before = _sha256(slick)
            sport_before = _sha256(sport)

            output = root / "diagnostic"
            report = run_native_tire_cross_family_diagnostic_from_directory(
                tires,
                output,
                candidate_limit=5,
            )

            self.assertEqual(report.status, "diagnostic_one_click_cross_family_signature_consistent")
            self.assertEqual(report.signature_comparison.unique_geometry_family_count, 2)
            self.assertEqual(report.family_export.exported_unique_geometry_count, 1)
            self.assertTrue(report.reference_copy_verified)
            self.assertTrue(report.source_archives_read_only_unchanged)
            self.assertFalse(report.production_mapping_enabled)
            self.assertEqual(_sha256(slick), slick_before)
            self.assertEqual(_sha256(sport), sport_before)
            self.assertTrue(Path(report.manifest_path).is_file())
            self.assertTrue(Path(report.comparison_report_path).is_file())
            self.assertTrue(Path(report.bundle_path).is_file())

            manifest = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["signature_comparison"]["unique_geometry_family_count"], 2)
            with zipfile.ZipFile(report.bundle_path, "r") as bundle:
                names = set(bundle.namelist())
            self.assertIn("reference/tire_slick.zip", names)
            self.assertIn("family_export/archives/tire_sport.zip", names)
            self.assertIn("native_tire_selector_signature_comparison.json", names)
            self.assertIn("native_tire_cross_family_diagnostic_manifest.json", names)

    def test_candidate_with_same_modelbin_identity_is_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tires = root / "tires"
            tires.mkdir()
            modelbin = _bundle()
            _write_tire(tires / "tire_slick.zip", "tireL_slick.modelbin", modelbin)
            _write_tire(tires / "tire_street.zip", "tireL_street.modelbin", modelbin)

            report = run_native_tire_cross_family_diagnostic_from_directory(
                tires,
                root / "diagnostic",
            )
            self.assertEqual(
                report.status,
                "diagnostic_one_click_insufficient_unique_families",
            )
            self.assertEqual(report.signature_comparison.unique_geometry_family_count, 1)
            self.assertFalse(report.production_mapping_enabled)

    def test_output_inside_native_tire_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tires = Path(directory) / "tires"
            tires.mkdir()
            _write_tire(tires / "tire_slick.zip", "tireL_slick.modelbin", _bundle())
            with self.assertRaisesRegex(TireCrossFamilyDiagnosticError, "outside"):
                run_native_tire_cross_family_diagnostic_from_directory(
                    tires,
                    tires / "diagnostic",
                )

    def test_missing_reference_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tires = root / "tires"
            tires.mkdir()
            _write_tire(tires / "tire_sport.zip", "tireL_sport.modelbin", _bundle())
            with self.assertRaisesRegex(TireCrossFamilyDiagnosticError, "reference"):
                run_native_tire_cross_family_diagnostic_from_directory(
                    tires,
                    root / "diagnostic",
                )


if __name__ == "__main__":
    unittest.main()
