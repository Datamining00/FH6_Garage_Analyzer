from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import unittest

from fh6garage.fh6_clivery import (
    compare_fls_project_to_flattened,
    decode_clivery_file,
    flatten_livery_scene,
    inflate_clivery,
    load_fls_project_bytes,
    semantic_project_from_fls_artifact,
)


REAL5_FLS_SHA256 = "be05f4ed0b53ce94b47f0dc2d0675d2b2202e579af4a77655b2ff5d8676b8175"
REAL5_FLS_UNCOMPRESSED_SHA256 = "b7dbd2bb95bba76bea4638068b9c8baa1729673c629f36d72d527afc6bd55fdd"
REAL5_CLIVERY_SHA256 = "564181e1657e7485281036e3b80492f2bce8183f88a9c24be044185c17003b9c"
REAL5_CLIVERY_INFLATED_SHA256 = "e77e0cd7ea5e9528011ce034c73f00aa8c051dadc75baf0d21b55f7b8cb06167"
REAL5_SECTION_COUNTS = (2, 3, 1, 1, 3, 0, 0, 0, 0, 0, 0)
REAL5_SHAPE_IDS = (2104, 2110, 2105, 2106, 2109, 101, 102, 101, 102, 103)


def transform(
    x: float = 0.0,
    y: float = 0.0,
    *,
    skew: float = 0.0,
) -> dict[str, float]:
    return {
        "x": x,
        "y": y,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "rotation": 0.0,
        "skew": skew,
    }


def shape(
    shape_id: int,
    x: float,
    y: float,
    stored_bgra: list[int],
    *,
    mask: bool = False,
    skew: float = 0.0,
) -> dict[str, object]:
    return {
        "kind": "shape",
        "id": f"layer_{shape_id}_{x}_{y}",
        "name": f"shape_{shape_id}",
        "locked": False,
        "visible": True,
        "opacity": 1.0,
        "mask": mask,
        "color": stored_bgra,
        "transform": transform(x, y, skew=skew),
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


def observed_controlled5_project() -> bytes:
    names = [
        "Front", "Back", "Top", "Left", "Right", "Spoiler",
        "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow",
    ]
    sections = [section(slot, name, []) for slot, name in enumerate(names)]
    sections[0]["children"] = [
        shape(2104, -131.50872, -32.17767, [0, 0, 255, 255], mask=True),
        shape(2110, -48.188806226019096, -3.8354996201763925, [255, 255, 255, 255]),
    ]
    # The uploaded pair does not contain the intended Group-boundary mask case:
    # Back is three direct Shapes. Keep that absence explicit in the fixture.
    sections[1]["children"] = [
        shape(2105, 917.3422215628693, 23.06261896326464, [255, 255, 255, 255]),
        shape(2106, 980.2985244272538, -21.706307518075505, [0, 0, 255, 255]),
        shape(2109, 963.5101769967514, 41.24999534630899, [255, 85, 0, 255]),
    ]
    sections[2]["children"] = [
        shape(101, 237.11062, 93.24571, [255, 85, 0, 255], skew=2.3),
    ]
    # This is color alpha 164 with node opacity still exactly 1.0; it is not a
    # non-unit opacity oracle.
    sections[3]["children"] = [
        shape(102, 237.11062, 93.24571, [255, 85, 0, 164]),
    ]
    sections[4]["children"] = [
        shape(101, 237.11061677613498, 93.24570867437433, [0, 0, 255, 255]),
        shape(102, 237.11061677613498, 93.24570867437433, [0, 255, 0, 255]),
        shape(103, 237.11061677613498, 93.24570867437433, [255, 0, 0, 255]),
    ]
    document = {
        "format": "fls_editor_project",
        "version": 3,
        "name": "Controlled5",
        "car_id": 2017,
        "is_livery": True,
        "root": {"children": sections},
    }
    return gzip.compress(json.dumps(document, separators=(",", ":")).encode("utf-8"), mtime=0)


class FLSControlledPair5Tests(unittest.TestCase):
    def test_observed_scene_covers_chromatic_mask_skew_alpha_and_direct_order(self) -> None:
        artifact = load_fls_project_bytes(observed_controlled5_project())
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.car_id, 2017)
        self.assertEqual(oracle.section_counts, REAL5_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in oracle.layers), REAL5_SHAPE_IDS)

        front = [layer for layer in oracle.layers if layer.section == "Front"]
        self.assertEqual([layer.type_word for layer in front], [2104, 2110])
        self.assertEqual([layer.mask for layer in front], [True, False])
        self.assertEqual(front[0].color_rgba, (255, 0, 0, 255))

        top = [layer for layer in oracle.layers if layer.section == "Top"]
        self.assertEqual(len(top), 1)
        self.assertAlmostEqual(top[0].transform[5], 2.3)

        left = [layer for layer in oracle.layers if layer.section == "Left"]
        self.assertEqual(left[0].color_rgba, (0, 85, 255, 164))

        right = [layer for layer in oracle.layers if layer.section == "Right"]
        self.assertEqual([layer.type_word for layer in right], [101, 102, 103])
        self.assertEqual(
            [layer.color_rgba for layer in right],
            [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)],
        )

    def test_real_controlled5_fls_clivery_pair_when_available(self) -> None:
        fls_value = os.environ.get("FH6_FLS_3SO_2017_MASK_SKEW_ORDER")
        clivery_value = os.environ.get("FH6_CLIVERY_2017_MASK_SKEW_ORDER")
        if (
            not fls_value
            or not clivery_value
            or not Path(fls_value).is_file()
            or not Path(clivery_value).is_file()
        ):
            self.skipTest(
                "set FH6_FLS_3SO_2017_MASK_SKEW_ORDER and FH6_CLIVERY_2017_MASK_SKEW_ORDER "
                "to the controlled pair-5 artifacts"
            )

        fls_path = Path(fls_value)
        clivery_path = Path(clivery_value)
        fls_raw = fls_path.read_bytes()
        clivery_raw = clivery_path.read_bytes()
        self.assertEqual(hashlib.sha256(fls_raw).hexdigest(), REAL5_FLS_SHA256)
        self.assertEqual(hashlib.sha256(clivery_raw).hexdigest(), REAL5_CLIVERY_SHA256)

        artifact = load_fls_project_bytes(fls_raw)
        self.assertEqual(artifact.uncompressed_sha256, REAL5_FLS_UNCOMPRESSED_SHA256)
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.section_counts, REAL5_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in oracle.layers), REAL5_SHAPE_IDS)

        # Pair 5 did not actually create the intended completed-Group boundary.
        back_children = artifact.document["root"]["children"][1]["children"]
        self.assertEqual([node["kind"] for node in back_children], ["shape", "shape", "shape"])
        # The alpha-164 layer still has editor node opacity 1.0.
        left_node = artifact.document["root"]["children"][3]["children"][0]
        self.assertEqual(left_node["opacity"], 1)
        self.assertEqual(left_node["color"], [255, 85, 0, 164])

        inflated, _container = inflate_clivery(clivery_raw)
        self.assertEqual(hashlib.sha256(inflated).hexdigest(), REAL5_CLIVERY_INFLATED_SHA256)
        self.assertEqual(inflated[110:112], b"\x01\x02")
        self.assertEqual(inflated[79 + 27:79 + 31], bytes((0, 0, 255, 255)))

        scene = decode_clivery_file(clivery_path)
        flattened = flatten_livery_scene(scene)
        report = compare_fls_project_to_flattened(oracle, flattened)
        self.assertTrue(report.match, report.to_dict())

        front = next(section for section in flattened.sections if section.name == "Front")
        self.assertEqual([layer.type_word for layer in front.layers], [2104, 2110])
        self.assertEqual(front.layers[0].color_rgba, (255, 0, 0, 255))
        self.assertTrue(front.layers[0].mask)
        self.assertEqual(front.layers[0].mask_evidence, ("shape_0102_trailing_state",))
        self.assertFalse(front.layers[1].mask)

        top = next(section for section in flattened.sections if section.name == "Top")
        self.assertEqual(top.layers[0].type_word, 101)
        self.assertAlmostEqual(top.layers[0].transform.skew, 2.299999952316284)

        left = next(section for section in flattened.sections if section.name == "Left")
        self.assertEqual(left.layers[0].color_rgba, (0, 85, 255, 164))

        right = next(section for section in flattened.sections if section.name == "Right")
        self.assertEqual([layer.type_word for layer in right.layers], [101, 102, 103])
        self.assertEqual([layer.source_offset for layer in right.layers], [399, 430, 462])
        self.assertEqual(
            [layer.color_rgba for layer in right.layers],
            [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)],
        )


if __name__ == "__main__":
    unittest.main()
