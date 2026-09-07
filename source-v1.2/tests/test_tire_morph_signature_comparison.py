from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
import zipfile

from fh6garage.preview3d.tire_morph_signature_comparison import (
    TireMorphSignatureComparisonError,
    compare_native_tire_selector_signatures,
    compare_selector_signature_sets,
    normalized_selector_signatures_from_states,
)
from tests.test_tire_morph_geometry import _bundle


def _state(minimum, maximum):
    return {"aabb": {"minimum": minimum, "maximum": maximum}}


def _slick_like_states(scale: float = 1.0):
    def scaled(values):
        return tuple(scale * value for value in values)

    return {
        "baseline": _state(scaled((-0.0032, -0.2248, -0.2247)), scaled((1.0032, 0.2248, 0.2247))),
        "selector0": _state(scaled((0.0, -0.4994, -0.4996)), scaled((1.0032, 0.4994, 0.4996))),
        "selector1": _state(scaled((-0.0032, -0.3296, -0.3291)), scaled((1.0032, 0.3296, 0.3291))),
        "selector2": _state(scaled((-0.1415, -0.1522, -0.1522)), scaled((1.1682, 0.1522, 0.1522))),
        "selector3": _state(scaled((0.0, -0.2248, -0.2247)), scaled((1.2970, 0.2248, 0.2247))),
        "selector4": _state(scaled((-0.2955, -0.2248, -0.2247)), scaled((1.0, 0.2248, 0.2247))),
    }


class TireMorphSignatureComparisonTests(unittest.TestCase):
    def test_normalization_removes_uniform_absolute_scale(self) -> None:
        reference = normalized_selector_signatures_from_states(_slick_like_states(1.0))
        candidate = normalized_selector_signatures_from_states(_slick_like_states(2.5))
        role_match, max_abs, rms, per_selector = compare_selector_signature_sets(reference, candidate)
        self.assertTrue(role_match)
        self.assertAlmostEqual(max_abs, 0.0, places=12)
        self.assertAlmostEqual(rms, 0.0, places=12)
        for value in per_selector.values():
            self.assertAlmostEqual(value, 0.0, places=12)

    def test_role_change_is_detected_even_when_dimensions_are_finite(self) -> None:
        reference = normalized_selector_signatures_from_states(_slick_like_states())
        altered = _slick_like_states()
        altered["selector4"] = _state((-0.0032, -0.2248, -0.2247), (1.2955, 0.2248, 0.2247))
        candidate = normalized_selector_signatures_from_states(altered)
        role_match, max_abs, _rms, per_selector = compare_selector_signature_sets(reference, candidate)
        self.assertFalse(role_match)
        self.assertGreater(max_abs, 0.0)
        self.assertGreater(per_selector[4], 0.0)

    def test_duplicate_geometry_archives_do_not_count_as_two_families(self) -> None:
        modelbin = _bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "tire_family_a.zip"
            second = root / "tire_family_b.zip"
            with zipfile.ZipFile(first, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("tireL_family_a.modelbin", modelbin)
            with zipfile.ZipFile(second, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("tireL_family_b.modelbin", modelbin)

            report = compare_native_tire_selector_signatures((first, second))
            self.assertEqual(report.unique_geometry_family_count, 1)
            self.assertEqual(
                report.status,
                "diagnostic_selector_signature_insufficient_unique_families",
            )
            self.assertFalse(report.production_mapping_enabled)
            self.assertTrue(report.comparisons[0].same_geometry_identity_as_reference)

    def test_invalid_tolerance_fails_closed(self) -> None:
        with self.assertRaisesRegex(TireMorphSignatureComparisonError, "quantitative_tolerance"):
            compare_native_tire_selector_signatures(("unused.zip",), quantitative_tolerance=-0.1)


if __name__ == "__main__":
    unittest.main()
