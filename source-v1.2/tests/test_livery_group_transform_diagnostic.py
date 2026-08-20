from __future__ import annotations

import copy
import unittest
from pathlib import Path

from fh6garage.livery_group_transform_diagnostic import _trace_flatten_call
from fh6garage.livery_preview import _load_backend


class GroupTransformDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decoder, _renderer = _load_backend()

    def _sample_tree(self):
        decoder = self.decoder
        root = decoder.GroupNode(
            transform=decoder.Transform(x=10.0, y=20.0, sx=2.0, sy=2.0, rotation=0.0),
            offset=8,
            source="livery_section",
            section="Right",
        )
        child = decoder.GroupNode(
            transform=decoder.Transform(x=5.0, y=-3.0, sx=0.5, sy=0.5, rotation=30.0),
            offset=40,
            source="markerless_group",
            section="Right",
        )
        shape = decoder.ShapeNode(
            shape_id=313,
            x=4.0,
            y=8.0,
            sx=1.2,
            sy=0.8,
            rotation=10.0,
            skew=0.1,
            color_rgba=(95, 87, 85, 255),
            offset=64,
            section="Right",
        )
        child.items.append(shape)
        root.items.append(child)
        return root

    def test_trace_reproduces_upstream_flatten_transform(self):
        root = self._sample_tree()
        flat = self.decoder.flatten_tree(root, layer_start=1000, section="Right")

        trace = _trace_flatten_call(
            self.decoder,
            root,
            copy.deepcopy(flat),
            layer_start=1000,
            section="Right",
            call_index=7,
        )

        self.assertEqual(trace["flat_layer_count"], 1)
        self.assertEqual(trace["traced_layer_count"], 1)
        self.assertEqual(trace["group_count"], 2)
        self.assertEqual(trace["max_group_depth"], 1)
        self.assertTrue(trace["trace_matches_flatten"])
        self.assertEqual(trace["mismatch_offsets"], [])

        layer = trace["layers"][0]
        self.assertEqual(layer["source_offset"], 1064)
        self.assertEqual(layer["section"], "Right")
        self.assertEqual(len(layer["group_chain"]), 2)
        self.assertEqual(layer["parent_group_id"], layer["group_chain"][-1])
        self.assertEqual(layer["color_rgba"], [95, 87, 85, 255])

        nested = trace["groups"][1]
        self.assertEqual(nested["parent_group_id"], trace["groups"][0]["group_id"])
        self.assertEqual(nested["descendant_layer_count"], 1)
        self.assertIsNotNone(nested["final_center_bounds"])

    def test_trace_does_not_mutate_tree_or_flattened_layers(self):
        root = self._sample_tree()
        before = self.decoder.flatten_tree(root, layer_start=0, section="Right")
        root_snapshot = (
            root.transform.x,
            root.transform.y,
            root.transform.sx,
            root.transform.sy,
            root.transform.rotation,
            root.items[0].transform.x,
            root.items[0].transform.y,
        )

        _trace_flatten_call(
            self.decoder,
            root,
            copy.deepcopy(before),
            layer_start=0,
            section="Right",
            call_index=0,
        )

        after = self.decoder.flatten_tree(root, layer_start=0, section="Right")
        self.assertEqual(before, after)
        self.assertEqual(
            root_snapshot,
            (
                root.transform.x,
                root.transform.y,
                root.transform.sx,
                root.transform.sy,
                root.transform.rotation,
                root.items[0].transform.x,
                root.items[0].transform.y,
            ),
        )

    def test_app_installs_group_trace_after_warning_only_baseline(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        baseline_pos = text.index("apply_livery_baseline_behavior_patch()")
        trace_pos = text.index("install_group_transform_diagnostic()")
        self.assertGreater(trace_pos, baseline_pos)


if __name__ == "__main__":
    unittest.main()
