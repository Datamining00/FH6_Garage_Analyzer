from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.livery_parent_ownership_diagnostic import summarize_ownership_call
from fh6garage.livery_preview import _load_backend


class ParentOwnershipDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decoder, _renderer = _load_backend()

    def test_records_implicit_parent_and_direct_child_groups(self):
        decoder = self.decoder
        root = decoder.GroupNode(source="section_root", offset=0)
        parent = decoder.GroupNode(
            transform=decoder.Transform(x=-360.5, y=-31.0, sx=0.9, sy=0.9, rotation=3.5),
            expected_children=2,
            source="implicit_bare_transform_pair",
            offset=100,
        )
        child_a = decoder.GroupNode(
            transform=decoder.Transform(x=0.0, y=2.0, sx=0.05, sy=0.05, rotation=0.0),
            expected_children=1,
            source="counted",
            offset=140,
        )
        child_b = decoder.GroupNode(
            transform=decoder.Transform(x=0.0, y=-4.5, sx=0.05, sy=0.05, rotation=0.0),
            expected_children=2,
            source="counted",
            offset=200,
        )
        parent.items.extend([child_a, child_b])
        root.items.append(parent)

        report = summarize_ownership_call(decoder, root, layer_start=1000, section="Right")
        self.assertEqual(report["implicit_parent_count"], 1)
        implicit = report["implicit_parents"][0]
        self.assertEqual(implicit["source_offset"], 1100)
        self.assertEqual(implicit["actual_children"], 2)
        self.assertEqual([item["source_offset"] for item in implicit["direct_children"]], [1140, 1200])
        self.assertEqual([item["source"] for item in implicit["direct_children"]], ["counted", "counted"])

    def test_root_children_are_recorded_without_mutation(self):
        decoder = self.decoder
        root = decoder.GroupNode(source="section_root", offset=0)
        child = decoder.GroupNode(expected_children=0, source="counted", offset=25)
        root.items.append(child)
        before = list(root.items)
        report = summarize_ownership_call(decoder, root, layer_start=500, section="Right")
        self.assertEqual(report["root_direct_children"][0]["source_offset"], 525)
        self.assertEqual(root.items, before)

    def test_app_wires_ownership_trace_after_structural_audit(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        audit_pos = text.index("install_livery_structural_parser_audit()")
        ownership_pos = text.index("install_livery_parent_ownership_diagnostic()")
        ui_pos = text.index("apply_v1_3_ui_patches(MainWindow)")
        self.assertGreater(ownership_pos, audit_pos)
        self.assertLess(ownership_pos, ui_pos)


if __name__ == "__main__":
    unittest.main()
