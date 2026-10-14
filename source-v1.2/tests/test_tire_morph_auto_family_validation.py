from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import unittest

from fh6garage.preview3d.tire_morph_auto_family_validation import (
    TireMorphAutoFamilyValidationError,
    validate_stock_tire_morph_families_auto,
)
from tests.test_tire_morph_cross_family_validation import _create_cross_family_fixture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TireMorphAutoFamilyValidationTests(unittest.TestCase):
    def test_selects_then_runs_cross_family_validation_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, archives = _create_cross_family_fixture(root)
            db_before = _sha256(database)
            archive_before = tuple(_sha256(path) for path in archives)

            report = validate_stock_tire_morph_families_auto(
                root,
                database,
                candidate_limit=2,
                min_unique_families=2,
            )

            self.assertEqual(_sha256(database), db_before)
            self.assertEqual(
                tuple(_sha256(path) for path in archives),
                archive_before,
            )

        self.assertEqual(report.selected_car_ids, (1229, 1006))
        self.assertEqual(report.selected_tire_model_names, ("Sport", "Street"))
        self.assertIsNotNone(report.validation)
        assert report.validation is not None
        self.assertEqual(report.validation.unique_family_count, 2)
        self.assertFalse(report.production_mapping_enabled)
        # The shared synthetic tire geometry intentionally does not reproduce
        # real stock radial deformation, so the automatic pipeline must remain
        # fail-closed after successfully completing both family validations.
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_auto_cross_family_not_corroborated",
        )

    def test_insufficient_candidates_skip_geometry_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, _archives = _create_cross_family_fixture(root)
            report = validate_stock_tire_morph_families_auto(
                root,
                database,
                exclude_model_names=("Sport",),
                candidate_limit=2,
                min_unique_families=2,
            )

        self.assertEqual(report.selected_car_ids, (1006,))
        self.assertEqual(report.selected_tire_model_names, ("Street",))
        self.assertIsNone(report.validation)
        self.assertFalse(report.production_mapping_enabled)
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_auto_cross_family_insufficient_candidates",
        )

    def test_candidate_limit_below_minimum_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            TireMorphAutoFamilyValidationError,
            "candidate_limit must be at least",
        ):
            validate_stock_tire_morph_families_auto(
                Path("unused"),
                Path("unused.sqlite"),
                candidate_limit=1,
                min_unique_families=2,
            )


if __name__ == "__main__":
    unittest.main()
