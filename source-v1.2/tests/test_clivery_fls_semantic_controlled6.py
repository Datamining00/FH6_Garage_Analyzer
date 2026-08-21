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


REAL6_FLS_SHA256 = "14092c91233dc6f50405486038ecd49377fbd14f3730549f97ef61e27ace1078"
REAL6_FLS_UNCOMPRESSED_SHA256 = "47eb35affee966238b2d2631946a8c9297dd4fcd4cb2b2c184088f881897e562"
REAL6_CLIVERY_SHA256 = "4b757a4c8f536a8b9f52854e3b64df711247726854c4bc38fa9d2b18e6bd82f3"
REAL6_CLIVERY_INFLATED_SHA256 = "09dbf9860f76f3ccd0464b98077f3664c96c785df8530578ddaaf58d2d5eabf1"
REAL6_UI_RIGHT_SCREENSHOT_SHA256 = "e0412ba5b74aa31aaf660dbaa060568914b4e9f89d25be68e8b85012ae2c0635"
REAL6_UI_LEFT_SCREENSHOT_SHA256 = "b3ee61873ce2a4c85ef78b7dd7006b2c974085ac294881bc4ebc45f585d89e57"
REAL6_SECTION_COUNTS = (0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0)
REAL6_SHAPE_IDS = (102, 101)


def transform() -> dict[str, float]:
    return {
        "x": 0.0,
        "y": 0.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "rotation": 0.0,
        "skew": 0.0,
    }


def shape(shape_id: int, stored_bgra: list[int], *, visible: bool) -> dict[str, object]:
    return {
        "kind": "shape",
        "id": f"layer_{shape_id}",
        "name": f"Primitives_0x{shape_id:04X}",
        "locked": False,
        "visible": visible,
        "opacity": 1.0,
        "mask": False,
        "color": stored_bgra,
        "transform": transform(),
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


def observed_controlled6_project() -> bytes:
    names = [
        "Front", "Back", "Top", "Left", "Right", "Spoiler",
        "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow",
    ]
    sections = [section(slot, name, []) for slot, name in enumerate(names)]
    # The saved project serializes the green circle under internal slot 3 / Left.
    sections[3]["children"] = [shape(102, [0, 255, 0, 255], visible=False)]
    # The saved project serializes the red square under internal slot 4 / Right.
    sections[4]["children"] = [shape(101, [0, 0, 255, 255], visible=True)]
    document = {
        "format": "fls_editor_project",
        "version": 3,
        "name": "Controlled6SideOracle",
        "car_id": 1124,
        "is_livery": True,
        "root": {"children": sections},
    }
    return gzip.compress(json.dumps(document, separators=(",", ":")).encode("utf-8"), mtime=0)


class FLSControlledPair6Tests(unittest.TestCase):
    def test_observed_internal_side_slots_are_stable(self) -> None:
        artifact = load_fls_project_bytes(observed_controlled6_project())
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.car_id, 1124)
        self.assertEqual(oracle.section_counts, REAL6_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in oracle.layers), REAL6_SHAPE_IDS)

        left = [layer for layer in oracle.layers if layer.section == "Left"]
        right = [layer for layer in oracle.layers if layer.section == "Right"]
        self.assertEqual([layer.type_word for layer in left], [102])
        self.assertEqual([layer.color_rgba for layer in left], [(0, 255, 0, 255)])
        self.assertEqual([layer.type_word for layer in right], [101])
        self.assertEqual([layer.color_rgba for layer in right], [(255, 0, 0, 255)])

    def test_real_controlled6_fls_clivery_pair_when_available(self) -> None:
        fls_value = os.environ.get("FH6_FLS_3SO_1124_SIDE_ORACLE")
        clivery_value = os.environ.get("FH6_CLIVERY_1124_SIDE_ORACLE")
        if (
            not fls_value
            or not clivery_value
            or not Path(fls_value).is_file()
            or not Path(clivery_value).is_file()
        ):
            self.skipTest(
                "set FH6_FLS_3SO_1124_SIDE_ORACLE and FH6_CLIVERY_1124_SIDE_ORACLE "
                "to the controlled pair-6 side-oracle artifacts"
            )

        fls_path = Path(fls_value)
        clivery_path = Path(clivery_value)
        fls_raw = fls_path.read_bytes()
        clivery_raw = clivery_path.read_bytes()
        self.assertEqual(hashlib.sha256(fls_raw).hexdigest(), REAL6_FLS_SHA256)
        self.assertEqual(hashlib.sha256(clivery_raw).hexdigest(), REAL6_CLIVERY_SHA256)

        artifact = load_fls_project_bytes(fls_raw)
        self.assertEqual(artifact.uncompressed_sha256, REAL6_FLS_UNCOMPRESSED_SHA256)
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.section_counts, REAL6_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in oracle.layers), REAL6_SHAPE_IDS)

        project_sections = artifact.document["root"]["children"]
        self.assertEqual(project_sections[3]["name"], "Left")
        self.assertEqual(project_sections[3]["livery_section_slot"], 3)
        self.assertEqual(project_sections[3]["children"][0]["visual"]["shape_id"], 102)
        self.assertEqual(project_sections[3]["children"][0]["color"], [0, 255, 0, 255])
        self.assertEqual(project_sections[4]["name"], "Right")
        self.assertEqual(project_sections[4]["livery_section_slot"], 4)
        self.assertEqual(project_sections[4]["children"][0]["visual"]["shape_id"], 101)
        self.assertEqual(project_sections[4]["children"][0]["color"], [0, 0, 255, 255])

        inflated, _container = inflate_clivery(clivery_raw)
        self.assertEqual(hashlib.sha256(inflated).hexdigest(), REAL6_CLIVERY_INFLATED_SHA256)
        # Exact direct Shape records from the supplied export.
        self.assertEqual(inflated[148:151], b"\x02\x66\x00")
        self.assertEqual(inflated[148 + 27:148 + 31], bytes((0, 255, 0, 255)))
        self.assertEqual(inflated[204:207], b"\x02\x65\x00")
        self.assertEqual(inflated[204 + 27:204 + 31], bytes((0, 0, 255, 255)))

        scene = decode_clivery_file(clivery_path)
        flattened = flatten_livery_scene(scene)
        report = compare_fls_project_to_flattened(oracle, flattened)
        self.assertTrue(report.match, report.to_dict())

        left = next(section for section in flattened.sections if section.name == "Left")
        right = next(section for section in flattened.sections if section.name == "Right")
        self.assertEqual([layer.type_word for layer in left.layers], [102])
        self.assertEqual([layer.color_rgba for layer in left.layers], [(0, 255, 0, 255)])
        self.assertEqual([layer.type_word for layer in right.layers], [101])
        self.assertEqual([layer.color_rgba for layer in right.layers], [(255, 0, 0, 255)])


if __name__ == "__main__":
    unittest.main()
