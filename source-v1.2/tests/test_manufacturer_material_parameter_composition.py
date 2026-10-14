from __future__ import annotations

import unittest

from fh6garage.preview3d.manufacturer_material_parameter_composition import (
    diagnose_manufacturer_material_parameter_composition,
)
from fh6garage.preview3d.material_shader_parameter_helper import (
    MaterialShaderParameterHelperError,
)


def _node(material: str, shader: str, *, nested=None):
    references = [
        {
            "status": "shader_resolved_exact",
            "payload": {"cache_path": shader},
        }
    ]
    if nested is not None:
        references.append({"status": "nested_material", "nested": nested})
    return {
        "asset": {"cache_path": material},
        "references": references,
    }


def _composed_helper() -> dict:
    return {
        "status": "material_shader_parameters_composed",
        "parser_integrity_status": "clean",
        "rendering_enabled": False,
        "game_data_modified": False,
    }


class ManufacturerMaterialParameterCompositionTests(unittest.TestCase):
    def test_composes_one_direct_exact_pair(self):
        traced = {"traces": [{"root": _node("a.materialbin", "b.shaderbin")}]}
        calls = []

        def analyze(material, shader):
            calls.append((material, shader))
            return _composed_helper()

        report = diagnose_manufacturer_material_parameter_composition(
            traced,
            analyze_parameters=analyze,
        )
        self.assertEqual(calls, [("a.materialbin", "b.shaderbin")])
        self.assertEqual(report["revision"], 2)
        self.assertEqual(report["target_count"], 1)
        self.assertEqual(report["composed_count"], 1)
        self.assertEqual(report["failed_count"], 0)
        self.assertEqual(
            report["status"],
            "manufacturer_material_shader_parameters_diagnosed",
        )
        self.assertFalse(report["rendering_enabled"])
        self.assertFalse(report["game_data_modified"])

    def test_duplicate_pairs_across_primitives_are_deduplicated(self):
        traced = {
            "traces": [
                {"root": _node("same.materialbin", "same.shaderbin")},
                {"root": _node("same.materialbin", "same.shaderbin")},
                {"root": _node("SAME.materialbin", "SAME.shaderbin")},
            ]
        }
        calls = []

        def analyze(material, shader):
            calls.append((material, shader))
            return _composed_helper()

        report = diagnose_manufacturer_material_parameter_composition(
            traced,
            analyze_parameters=analyze,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["target_count"], 1)
        self.assertEqual(report["composed_count"], 1)

    def test_nested_material_uses_immediate_material_cache_path(self):
        nested = _node("child.materialbin", "child.shaderbin")
        root = {
            "asset": {"cache_path": "root.materialbin"},
            "references": [
                {
                    "status": "nested_materialbin",
                    "nested": nested,
                }
            ],
        }
        calls = []

        def analyze(material, shader):
            calls.append((material, shader))
            return _composed_helper()

        report = diagnose_manufacturer_material_parameter_composition(
            {"traces": [{"root": root}]},
            analyze_parameters=analyze,
        )
        self.assertEqual(calls, [("child.materialbin", "child.shaderbin")])
        self.assertEqual(report["target_count"], 1)

    def test_composed_status_without_clean_integrity_is_rejected(self):
        traced = {"traces": [{"root": _node("a.materialbin", "b.shaderbin")}]} 

        for integrity in (None, "failed"):
            with self.subTest(integrity=integrity):
                def analyze(_material, _shader, integrity=integrity):
                    result = {"status": "material_shader_parameters_composed"}
                    if integrity is not None:
                        result["parser_integrity_status"] = integrity
                    return result

                report = diagnose_manufacturer_material_parameter_composition(
                    traced,
                    analyze_parameters=analyze,
                )
                self.assertEqual(report["composed_count"], 0)
                self.assertEqual(report["failed_count"], 1)
                self.assertEqual(
                    report["status"],
                    "manufacturer_material_shader_parameters_incomplete",
                )
                self.assertIn(
                    "parser_integrity_not_clean",
                    report["pairs"][0]["detail"],
                )

    def test_helper_failure_is_reported_fail_closed(self):
        traced = {"traces": [{"root": _node("a.materialbin", "b.shaderbin")}]}

        def analyze(_material, _shader):
            raise MaterialShaderParameterHelperError("decode failed")

        report = diagnose_manufacturer_material_parameter_composition(
            traced,
            analyze_parameters=analyze,
        )
        self.assertEqual(report["composed_count"], 0)
        self.assertEqual(report["failed_count"], 1)
        self.assertEqual(
            report["status"],
            "manufacturer_material_shader_parameters_incomplete",
        )
        self.assertFalse(report["rendering_enabled"])
        self.assertFalse(report["rendering_applied"])
        self.assertFalse(report["game_data_modified"])


if __name__ == "__main__":
    unittest.main()
