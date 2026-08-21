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
    load_fls_project_bytes,
    semantic_project_from_fls_artifact,
)


REAL3_FLS_SHA256 = "1afa34a9142fa937a419264b7ae92f003fb1acb08b93cfb1fe7c958878303b2c"
REAL3_FLS_UNCOMPRESSED_SHA256 = "11338cc1b1308c1ba507d053595fc5508662dd170a535c9c32305dab1c016e07"
REAL3_CLIVERY_SHA256 = "b2751da36f17f7fbd80c5825261237820d9bad0b10bacff9206a36437ce74b1e"
REAL3_SECTION_COUNTS = (2, 3, 1, 3, 1, 0, 0, 0, 0, 0, 0)
REAL3_SHAPE_IDS = (2104, 2105, 2126, 2135, 2137, 2217, 2106, 2110, 2123, 2116)


def transform(
    x: float = 0.0,
    y: float = 0.0,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation: float = 0.0,
    skew: float = 0.0,
) -> dict[str, float]:
    return {
        "x": x,
        "y": y,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "rotation": rotation,
        "skew": skew,
    }


def shape(
    shape_id: int,
    x: float,
    y: float,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation: float = 0.0,
    mask: bool = False,
    visible: bool = True,
) -> dict[str, object]:
    return {
        "kind": "shape",
        "id": f"layer_{shape_id}",
        "name": f"shape_{shape_id}",
        "locked": False,
        "visible": visible,
        "opacity": 1.0,
        "mask": mask,
        "color": [255, 255, 255, 255],
        "transform": transform(
            x,
            y,
            scale_x=scale_x,
            scale_y=scale_y,
            rotation=rotation,
        ),
        "visual": {"kind": "vector", "shape_id": shape_id},
        "debug": {},
    }


def group(children: list[dict[str, object]]) -> dict[str, object]:
    return {
        "kind": "group",
        "id": "group_controlled3",
        "name": "Group",
        "locked": False,
        "visible": True,
        "opacity": 1.0,
        "transform": transform(),
        "children": children,
        "is_livery_section": False,
        "livery_section_slot": -1,
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


def observed_controlled3_project() -> bytes:
    """Synthetic copy of the observed user-produced pair-3 scene semantics.

    The user selected the Left group and invoked FLS Flip Selection once. In the
    saved v3 project the group frame remains identity; FLS has already rebaked the
    world-space horizontal flip into the two child Shape transforms.
    """
    names = [
        "Front", "Back", "Top", "Left", "Right", "Spoiler",
        "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow",
    ]
    sections = [section(slot, name, []) for slot, name in enumerate(names)]
    sections[0]["children"] = [
        shape(2104, -36.22635908198322, -149.77847950467344, visible=False),
        shape(2105, -36.22635908198322, -149.77847950467344, visible=False),
    ]
    sections[1]["children"] = [
        shape(2126, -255.99764200675622, -136.2852200353734, visible=False),
        shape(2135, 58.158259997698224, -4.009050770340082, visible=False),
        shape(
            2137,
            -239.4631208486271,
            181.17758620070686,
            scale_y=-1.0,
            rotation=180.0,
            visible=False,
        ),
    ]
    sections[2]["children"] = [
        shape(2217, -36.22636, -149.77848, mask=True, visible=False),
    ]
    sections[3]["children"] = [
        group([
            shape(
                2106,
                -183.066794619735,
                -53.664739879963065,
                scale_y=-1.0,
                rotation=180.0,
            ),
            shape(
                2110,
                49.208076139981586,
                -205.8448276190877,
                scale_y=-1.0,
                rotation=180.0,
            ),
        ]),
        shape(
            2123,
            -390.20176629069374,
            -280.35500616142804,
            rotation=45.280401250039816,
        ),
    ]
    sections[4]["children"] = [
        shape(2116, -36.22635908198322, -149.77847950467344, visible=False),
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


class FLSControlledPair3Tests(unittest.TestCase):
    def project(self):
        return semantic_project_from_fls_artifact(load_fls_project_bytes(observed_controlled3_project()))

    def test_group_flip_is_rebaked_into_child_shape_transforms(self) -> None:
        artifact = load_fls_project_bytes(observed_controlled3_project())
        left_group = artifact.document["root"]["children"][3]["children"][0]
        self.assertEqual(left_group["kind"], "group")
        self.assertEqual(left_group["transform"], transform())

        children = left_group["children"]
        self.assertEqual([child["visual"]["shape_id"] for child in children], [2106, 2110])
        self.assertEqual([child["transform"]["rotation"] for child in children], [180.0, 180.0])
        self.assertEqual([child["transform"]["scale_y"] for child in children], [-1.0, -1.0])

        project = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(project.section_counts, REAL3_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in project.layers), REAL3_SHAPE_IDS)

        left = [layer for layer in project.layers if layer.section == "Left"]
        self.assertEqual([layer.type_word for layer in left], [2106, 2110, 2123])
        self.assertAlmostEqual(left[0].transform[0], -183.066794619735)
        self.assertAlmostEqual(left[0].transform[1], -53.664739879963065)
        self.assertEqual(left[0].transform[2:5], (-1.0, 1.0, 0.0))
        self.assertAlmostEqual(left[1].transform[0], 49.208076139981586)
        self.assertAlmostEqual(left[1].transform[1], -205.8448276190877)
        self.assertEqual(left[1].transform[2:5], (-1.0, 1.0, 0.0))

    def test_real_controlled3_fls_clivery_pair_when_available(self) -> None:
        fls_value = os.environ.get("FH6_FLS_3SO_2017_GROUPFLIP")
        clivery_value = os.environ.get("FH6_CLIVERY_2017_GROUPFLIP")
        if (
            not fls_value
            or not clivery_value
            or not Path(fls_value).is_file()
            or not Path(clivery_value).is_file()
        ):
            self.skipTest(
                "set FH6_FLS_3SO_2017_GROUPFLIP and FH6_CLIVERY_2017_GROUPFLIP "
                "to the controlled FLS group-flip pair"
            )

        fls_path = Path(fls_value)
        clivery_path = Path(clivery_value)
        self.assertEqual(hashlib.sha256(fls_path.read_bytes()).hexdigest(), REAL3_FLS_SHA256)
        self.assertEqual(hashlib.sha256(clivery_path.read_bytes()).hexdigest(), REAL3_CLIVERY_SHA256)

        artifact = load_fls_project_bytes(fls_path.read_bytes())
        self.assertEqual(artifact.uncompressed_sha256, REAL3_FLS_UNCOMPRESSED_SHA256)
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.section_counts, REAL3_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in oracle.layers), REAL3_SHAPE_IDS)

        left_group = artifact.document["root"]["children"][3]["children"][0]
        self.assertEqual(left_group["transform"], transform())

        scene = decode_clivery_file(clivery_path)
        flattened = flatten_livery_scene(scene)
        report = compare_fls_project_to_flattened(oracle, flattened)
        self.assertTrue(report.match, report.to_dict())

        left = next(section for section in flattened.sections if section.name == "Left")
        reflected = [layer for layer in left.layers if layer.type_word in (2106, 2110)]
        self.assertEqual([layer.type_word for layer in reflected], [2106, 2110])
        self.assertTrue(all(layer.transform.sx < 0.0 and layer.transform.sy > 0.0 for layer in reflected))


if __name__ == "__main__":
    unittest.main()
