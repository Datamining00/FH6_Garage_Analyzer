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


REAL2_FLS_SHA256 = "999c619a062c8c68aa7f3f41ca17579a43e43b76bd25d3c1a94e693021ee9e53"
REAL2_FLS_UNCOMPRESSED_SHA256 = "10e9299f99951f5df004373f292c86bbc5df8845ef5da09545ed6beb632122ac"
REAL2_CLIVERY_SHA256 = "4bc0e733963f64fef2756932873bc315676e377aad29482094049887182860b6"
REAL2_SECTION_COUNTS = (2, 3, 1, 3, 1, 0, 0, 0, 0, 0, 0)
REAL2_SHAPE_IDS = (2104, 2105, 2126, 2135, 2137, 2217, 2106, 2110, 2123, 2116)


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
        "id": "group_controlled2",
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


def observed_controlled2_project() -> bytes:
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
        shape(2126, -255.99764200675622, -136.2852200353734),
        shape(2135, 58.158259997698224, -4.009050770340082),
        shape(
            2137,
            -239.4631208486271,
            181.17758620070686,
            scale_x=1.0,
            scale_y=-1.0,
            rotation=180.0,
        ),
    ]
    sections[2]["children"] = [
        shape(2217, -36.22636, -149.77848, mask=True, visible=False),
    ]
    sections[3]["children"] = [
        group([
            shape(2106, 49.208076139981586, -53.664739879963065, visible=False),
            shape(2110, -183.066794619735, -205.8448276190877, visible=False),
        ]),
        shape(
            2123,
            -390.20176629069374,
            -280.35500616142804,
            rotation=45.280401250039816,
            visible=False,
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


class FLSControlledPair2Tests(unittest.TestCase):
    def project(self):
        return semantic_project_from_fls_artifact(load_fls_project_bytes(observed_controlled2_project()))

    def test_controlled2_scene_maps_reflection_mask_and_rotation(self) -> None:
        project = self.project()
        self.assertEqual(project.car_id, 2017)
        self.assertEqual(project.section_counts, REAL2_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in project.layers), REAL2_SHAPE_IDS)

        reflected = next(layer for layer in project.layers if layer.type_word == 2137)
        self.assertAlmostEqual(reflected.transform[0], -239.4631208486271)
        self.assertAlmostEqual(reflected.transform[1], 181.17758620070686)
        self.assertEqual(reflected.transform[2:5], (-1.0, 1.0, 0.0))

        masked = next(layer for layer in project.layers if layer.type_word == 2217)
        self.assertTrue(masked.mask)

        rotated = next(layer for layer in project.layers if layer.type_word == 2123)
        self.assertAlmostEqual(rotated.transform[4], 45.280401250039816)

    def test_real_controlled2_fls_clivery_pair_when_available(self) -> None:
        fls_value = os.environ.get("FH6_FLS_3SO_2017_CONTROLLED2")
        clivery_value = os.environ.get("FH6_CLIVERY_2017_CONTROLLED2")
        if (
            not fls_value
            or not clivery_value
            or not Path(fls_value).is_file()
            or not Path(clivery_value).is_file()
        ):
            self.skipTest(
                "set FH6_FLS_3SO_2017_CONTROLLED2 and FH6_CLIVERY_2017_CONTROLLED2 "
                "to the reflection/mask/rotation controlled pair"
            )

        fls_path = Path(fls_value)
        clivery_path = Path(clivery_value)
        self.assertEqual(hashlib.sha256(fls_path.read_bytes()).hexdigest(), REAL2_FLS_SHA256)
        self.assertEqual(hashlib.sha256(clivery_path.read_bytes()).hexdigest(), REAL2_CLIVERY_SHA256)

        artifact = load_fls_project_bytes(fls_path.read_bytes())
        self.assertEqual(artifact.uncompressed_sha256, REAL2_FLS_UNCOMPRESSED_SHA256)
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.section_counts, REAL2_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in oracle.layers), REAL2_SHAPE_IDS)

        scene = decode_clivery_file(clivery_path)
        flattened = flatten_livery_scene(scene)
        report = compare_fls_project_to_flattened(oracle, flattened)
        self.assertTrue(report.match, report.to_dict())

        top = next(section for section in flattened.sections if section.name == "Top")
        self.assertEqual(top.mask_source_offsets, (287,))
        self.assertEqual(top.layers[0].mask_evidence, ("section_terminal_state_01",))


if __name__ == "__main__":
    unittest.main()
