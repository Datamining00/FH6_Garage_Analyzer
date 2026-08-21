from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import unittest

from fh6garage.fh6_clivery import (
    FLSSemanticError,
    compare_fls_project_to_flattened,
    decode_clivery_file,
    flatten_livery_scene,
    load_fls_project_bytes,
    semantic_project_from_fls_artifact,
)


REAL_FLS_SHA256 = "2b7edae070afce33360ce87087045f8fc84d9f5714d153d89c8ccb8c886fc4f4"
REAL_FLS_UNCOMPRESSED_SHA256 = "2fa99cb36a5321c8449239638358891062cbe6490f8f89823bd6b58dc501c69a"
REAL_CLIVERY_SHA256 = "bd15497668848ad2a9ecefb71105f31953208f97a308866c1519ee1bdf076476"
REAL_SECTION_COUNTS = (2, 0, 0, 2, 1, 0, 0, 0, 0, 0, 0)


def transform(x: float = 0.0, y: float = 0.0) -> dict[str, float]:
    return {"x": x, "y": y, "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0, "skew": 0.0}


def shape(shape_id: int, x: float, y: float, *, visible: bool = True) -> dict[str, object]:
    return {
        "kind": "shape",
        "id": f"layer_{shape_id}",
        "name": f"shape_{shape_id}",
        "locked": False,
        "visible": visible,
        "opacity": 1.0,
        "mask": False,
        "color": [255, 255, 255, 255],
        "transform": transform(x, y),
        "visual": {"kind": "vector", "shape_id": shape_id},
        "debug": {},
    }


def section(slot: int, name: str, children: list[dict[str, object]]) -> dict[str, object]:
    return {
        "kind": "group",
        "id": f"section_{slot}",
        "name": name,
        "locked": False,
        "visible": True,
        "opacity": 1.0,
        "transform": transform(),
        "children": children,
        "is_livery_section": True,
        "livery_section_slot": slot,
        "debug": {},
    }


def observed_v3_project() -> bytes:
    names = [
        "Front", "Back", "Top", "Left", "Right", "Spoiler",
        "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow",
    ]
    sections = [section(slot, name, []) for slot, name in enumerate(names)]
    sections[0]["children"] = [
        shape(2104, -36.22635908198322, -149.77847950467344, visible=False),
        shape(2105, -36.22635908198322, -149.77847950467344, visible=False),
    ]
    sections[3]["children"] = [
        {
            "kind": "group",
            "id": "group_12",
            "name": "Group",
            "locked": False,
            "visible": True,
            "opacity": 1.0,
            "transform": transform(),
            "children": [
                shape(2106, 49.208076139981586, -53.664739879963065),
                shape(2110, -183.066794619735, -205.8448276190877),
            ],
            "is_livery_section": False,
            "livery_section_slot": -1,
            "debug": {},
        }
    ]
    sections[4]["children"] = [
        shape(2116, -36.22635908198322, -149.77847950467344, visible=False)
    ]
    document = {
        "format": "fls_editor_project",
        "version": 3,
        "name": "Untitled",
        "car_id": 2017,
        "is_livery": True,
        "root": {"children": sections},
    }
    return gzip.compress(json.dumps(document, separators=(",", ":")).encode("utf-8"), mtime=0)


class FLSSemanticTests(unittest.TestCase):
    def project(self):
        return semantic_project_from_fls_artifact(load_fls_project_bytes(observed_v3_project()))

    def test_observed_v3_scene_maps_to_five_semantic_leaves(self) -> None:
        project = self.project()
        self.assertEqual(project.car_id, 2017)
        self.assertEqual(project.section_counts, REAL_SECTION_COUNTS)
        self.assertEqual([layer.type_word for layer in project.layers], [2104, 2105, 2106, 2110, 2116])
        self.assertEqual(
            [layer.parent_path for layer in project.layers],
            [(0, 0), (0, 1), (3, 0, 0), (3, 0, 1), (4, 0)],
        )
        self.assertTrue(all(layer.source_offset is None for layer in project.layers))
        self.assertTrue(all(layer.mask is False for layer in project.layers))
        self.assertTrue(all(layer.color_rgba == (255, 255, 255, 255) for layer in project.layers))

    def test_hidden_editor_leaves_are_not_dropped_from_semantic_oracle(self) -> None:
        project = self.project()
        self.assertEqual([layer.type_word for layer in project.layers[:2]], [2104, 2105])
        self.assertEqual(project.layers[-1].type_word, 2116)

    def test_effective_nested_group_paths_and_positions_are_preserved(self) -> None:
        project = self.project()
        left = [layer for layer in project.layers if layer.section == "Left"]
        self.assertEqual([layer.parent_path for layer in left], [(3, 0, 0), (3, 0, 1)])
        self.assertAlmostEqual(left[0].transform[0], 49.208076139981586)
        self.assertAlmostEqual(left[0].transform[1], -53.664739879963065)
        self.assertAlmostEqual(left[1].transform[0], -183.066794619735)
        self.assertAlmostEqual(left[1].transform[1], -205.8448276190877)

    def test_nonconformal_group_fails_closed(self) -> None:
        artifact = load_fls_project_bytes(observed_v3_project())
        artifact.document["root"]["children"][3]["children"][0]["transform"]["scale_y"] = 2.0
        with self.assertRaises(FLSSemanticError):
            semantic_project_from_fls_artifact(artifact)

    def test_group_skew_fails_closed(self) -> None:
        artifact = load_fls_project_bytes(observed_v3_project())
        artifact.document["root"]["children"][3]["children"][0]["transform"]["skew"] = 1.0
        with self.assertRaises(FLSSemanticError):
            semantic_project_from_fls_artifact(artifact)

    def test_nonvector_visual_fails_closed(self) -> None:
        artifact = load_fls_project_bytes(observed_v3_project())
        artifact.document["root"]["children"][0]["children"][0]["visual"]["kind"] = "raster"
        with self.assertRaises(FLSSemanticError):
            semantic_project_from_fls_artifact(artifact)

    def test_nonunit_opacity_fails_closed(self) -> None:
        artifact = load_fls_project_bytes(observed_v3_project())
        artifact.document["root"]["children"][0]["children"][0]["opacity"] = 0.5
        with self.assertRaises(FLSSemanticError):
            semantic_project_from_fls_artifact(artifact)

    def test_real_controlled_fls_clivery_pair_when_available(self) -> None:
        fls_value = os.environ.get("FH6_FLS_3SO_2017")
        clivery_value = os.environ.get("FH6_CLIVERY_2017")
        if not fls_value or not clivery_value or not Path(fls_value).is_file() or not Path(clivery_value).is_file():
            self.skipTest("set FH6_FLS_3SO_2017 and FH6_CLIVERY_2017 to the controlled exported pair")

        fls_path = Path(fls_value)
        clivery_path = Path(clivery_value)
        self.assertEqual(hashlib.sha256(fls_path.read_bytes()).hexdigest(), REAL_FLS_SHA256)
        self.assertEqual(hashlib.sha256(clivery_path.read_bytes()).hexdigest(), REAL_CLIVERY_SHA256)

        artifact = load_fls_project_bytes(fls_path.read_bytes())
        self.assertEqual(artifact.uncompressed_sha256, REAL_FLS_UNCOMPRESSED_SHA256)
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.section_counts, REAL_SECTION_COUNTS)

        scene = decode_clivery_file(clivery_path)
        flattened = flatten_livery_scene(scene)
        report = compare_fls_project_to_flattened(oracle, flattened)
        self.assertTrue(report.match, report.to_dict())


if __name__ == "__main__":
    unittest.main()
