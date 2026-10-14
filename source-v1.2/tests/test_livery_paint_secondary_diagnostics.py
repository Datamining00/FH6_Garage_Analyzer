from __future__ import annotations

import unittest

import numpy as np

from fh6garage.preview3d.livery_paint_secondary_diagnostics import (
    build_livery_paint_secondary_diagnostics,
)


BODY = 0xF7DBE8A7C839A675
HOOD = 0x6AC1E9D87FE5D953


def _record(
    *,
    material_hash=BODY,
    primary_enabled=False,
    secondary_enabled=True,
    secondary_rgba=(32, 64, 128, 255),
    selector=0xFFFFFFFF,
    finish=51,
):
    return {
        "material_identifier_u64_le": material_hash,
        "primary_color_enabled": bool(primary_enabled),
        "secondary_color_enabled": bool(secondary_enabled),
        "secondary_rgba": list(secondary_rgba),
        "manufacturer_color_selector": selector,
        "finish_code": finish,
    }


def _report(records):
    return {"status": "paint_descriptor_parsed", "records": list(records)}


def _palette(*, secondary=(0.7, 0.8, 0.9), secondary_present=True):
    return {
        "status": "manufacturer_colors_parsed",
        "groups": [
            {
                "index": 0,
                "entry_count": 2,
                "entries": [
                    {"index": 0, "material_names": ["carpaint"], "preview_color": [0.1, 0.1, 0.1], "path": "a.swatchbin"},
                    {"index": 1, "material_names": ["carpaint2"], "preview_color": [0.2, 0.2, 0.2], "path": "b.swatchbin"},
                ],
                "primary_group_preview_present": True,
                "primary_group_preview_color": [0.2, 0.4, 0.6],
                "secondary_group_preview_present": bool(secondary_present),
                "secondary_group_preview_color": list(secondary),
            }
        ],
    }


class LiveryPaintSecondaryDiagnosticsTests(unittest.TestCase):
    def test_custom_secondary_replaces_manufacturer_secondary_diagnostically_only_when_factory_gate_is_open(self):
        report = build_livery_paint_secondary_diagnostics(
            _report([_record(selector=0, secondary_enabled=True, secondary_rgba=(32, 64, 128, 255))]),
            _palette(secondary=(0.7, 0.8, 0.9)),
        )
        row = report["records"][0]
        expected = np.power(np.asarray([32, 64, 128], dtype=np.float64) / 255.0, 2.2)
        np.testing.assert_allclose(row["secondary_linear_rgb_candidate"], expected, atol=1e-12)
        self.assertFalse(report["global_custom_primary_active"])
        self.assertEqual(report["manufacturer_global_gate"], "manufacturer_secondary_allowed")
        self.assertEqual(row["secondary_source_precedence"], "custom_secondary_override")
        self.assertEqual(row["secondary_status"], "custom_secondary_preserved_deferred")
        self.assertEqual(row["manufacturer_secondary"]["status"], "manufacturer_secondary_linear_preserved")
        self.assertFalse(row["rendering_enabled"])
        self.assertFalse(report["rendering_applied"])

    def test_manufacturer_secondary_is_preserved_when_custom_secondary_is_disabled(self):
        report = build_livery_paint_secondary_diagnostics(
            _report([_record(selector=0, secondary_enabled=False)]),
            _palette(secondary=(0.15, 0.25, 0.35)),
        )
        row = report["records"][0]
        self.assertEqual(row["secondary_source_precedence"], "manufacturer_group_trailer")
        self.assertEqual(row["secondary_status"], "manufacturer_secondary_preserved_deferred")
        np.testing.assert_allclose(row["secondary_linear_rgb_candidate"], [0.15, 0.25, 0.35], atol=1e-12)
        self.assertEqual(row["manufacturer_secondary"]["group_index"], 0)
        self.assertEqual(row["manufacturer_secondary"]["entry_count"], 2)
        self.assertFalse(row["rendering_enabled"])

    def test_any_explicit_custom_primary_globally_suppresses_manufacturer_secondary(self):
        report = build_livery_paint_secondary_diagnostics(
            _report([
                _record(material_hash=BODY, primary_enabled=True, secondary_enabled=False, selector=0xFFFFFFFF),
                _record(material_hash=HOOD, primary_enabled=False, secondary_enabled=False, selector=0),
            ]),
            _palette(secondary=(0.15, 0.25, 0.35)),
        )
        row = report["records"][1]
        self.assertTrue(report["global_custom_primary_active"])
        self.assertEqual(report["manufacturer_global_gate"], "suppressed_by_explicit_custom_primary")
        self.assertEqual(row["secondary_source_precedence"], "manufacturer_group_trailer")
        self.assertEqual(row["secondary_status"], "manufacturer_secondary_suppressed_by_global_custom_paint")
        self.assertIsNone(row["secondary_linear_rgb_candidate"])
        self.assertEqual(
            row["manufacturer_secondary"]["status"],
            "manufacturer_secondary_suppressed_by_global_custom_paint",
        )
        self.assertFalse(report["rendering_enabled"])

    def test_custom_secondary_remains_preserved_when_manufacturer_is_globally_suppressed(self):
        report = build_livery_paint_secondary_diagnostics(
            _report([
                _record(material_hash=BODY, primary_enabled=True, secondary_enabled=False),
                _record(material_hash=HOOD, secondary_enabled=True, secondary_rgba=(10, 20, 30, 255), selector=0),
            ]),
            _palette(),
        )
        row = report["records"][1]
        expected = np.power(np.asarray([10, 20, 30], dtype=np.float64) / 255.0, 2.2)
        np.testing.assert_allclose(row["secondary_linear_rgb_candidate"], expected, atol=1e-12)
        self.assertEqual(row["secondary_source_precedence"], "custom_secondary_override")
        self.assertEqual(row["secondary_status"], "custom_secondary_preserved_deferred")
        self.assertEqual(
            row["manufacturer_secondary"]["status"],
            "manufacturer_secondary_suppressed_by_global_custom_paint",
        )

    def test_invalid_enabled_custom_secondary_does_not_fall_back_to_manufacturer(self):
        report = build_livery_paint_secondary_diagnostics(
            _report([_record(selector=0, secondary_enabled=True, secondary_rgba=(999, 0, 0, 255))]),
            _palette(secondary=(0.2, 0.3, 0.4)),
        )
        row = report["records"][0]
        self.assertEqual(row["secondary_source_precedence"], "custom_secondary_override")
        self.assertEqual(row["secondary_status"], "custom_secondary_invalid_deferred")
        self.assertIsNone(row["secondary_linear_rgb_candidate"])
        self.assertEqual(row["manufacturer_secondary"]["status"], "manufacturer_secondary_linear_preserved")

    def test_finish_code_is_preserved_raw_but_no_mix_or_shader_semantics_are_enabled(self):
        report = build_livery_paint_secondary_diagnostics(_report([_record(finish=51)]))
        row = report["records"][0]
        self.assertEqual(row["finish_code_raw"], 51)
        self.assertEqual(row["finish_status"], "raw_finish_code_preserved_deferred")
        self.assertEqual(row["mixing_status"], "secondary_mix_and_finish_shader_deferred")
        self.assertFalse(report["rendering_enabled"])
        self.assertIn("No secondary mixing", report["interpretation_boundary"])

    def test_duplicate_material_identifiers_remain_binding_ambiguous(self):
        report = build_livery_paint_secondary_diagnostics(
            _report([_record(material_hash=BODY), _record(material_hash=BODY, secondary_rgba=(1, 2, 3, 255))])
        )
        self.assertEqual(report["duplicate_material_identifiers"], [f"0x{BODY:016X}"])
        self.assertEqual(report["records"][0]["binding_status"], "ambiguous_duplicate_material_identifier")
        self.assertEqual(report["records"][1]["binding_status"], "ambiguous_duplicate_material_identifier")
        self.assertTrue(any("binding-ambiguous" in issue for issue in report["issues"]))

    def test_unresolved_paint_provenance_fails_closed(self):
        report = build_livery_paint_secondary_diagnostics(
            {"status": "paint_header_unresolved", "records": []},
            _palette(),
        )
        self.assertEqual(report["status"], "secondary_finish_provenance_unavailable")
        self.assertEqual(report["records"], [])
        self.assertEqual(report["manufacturer_global_gate"], "unknown")
        self.assertFalse(report["rendering_enabled"])
        self.assertFalse(report["rendering_applied"])


if __name__ == "__main__":
    unittest.main()
