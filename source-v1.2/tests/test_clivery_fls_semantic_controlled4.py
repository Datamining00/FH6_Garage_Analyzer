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


REAL4_FLS_SHA256 = "0f143449078f74820bda819a043dac6d755cc6cfcf1cbea83ae457df17425029"
REAL4_FLS_UNCOMPRESSED_SHA256 = "888f8572f1eb013d9f1902e3dd2a5986d50fe3d3d23cfe515f95b322db616126"
REAL4_CLIVERY_SHA256 = "1c48aa8e3acd6f659aae1ac4f821b7ef1a26ba9c8932aa5c73d73eb6f51f7f33"
REAL4_CLIVERY_INFLATED_SHA256 = "ce42cae71b455922ba11685e8ed2972ba77096e5a069c80c92d7b5cc84c58dd9"
REAL4_SECTION_COUNTS = (2, 3, 1, 3, 1, 0, 0, 0, 0, 0, 0)
REAL4_SHAPE_IDS = (2104, 2105, 2126, 2135, 2137, 2217, 2106, 2110, 2123, 2116)


def transform(x: float = 0.0, y: float = 0.0) -> dict[str, float]:
    return {
        "x": x,
        "y": y,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "rotation": 0.0,
        "skew": 0.0,
    }


def observed_chromatic_mask_project() -> bytes:
    names = [
        "Front", "Back", "Top", "Left", "Right", "Spoiler",
        "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow",
    ]
    sections = []
    for slot, name in enumerate(names):
        sections.append(
            {
                "kind": "group",
                "id": f"section_{slot}",
                "name": name,
                "locked": False,
                "visible": True,
                "opacity": 1.0,
                "transform": transform(),
                "children": [],
                "is_livery_section": True,
                "livery_section_slot": slot,
                "debug": {},
            }
        )
    sections[2]["children"] = [
        {
            "kind": "shape",
            "id": "chromatic_mask_2217",
            "name": "shape_2217",
            "locked": False,
            "visible": False,
            "opacity": 1.0,
            "mask": True,
            "color": [255, 85, 0, 255],
            "transform": transform(-36.22636, -149.77848),
            "visual": {"kind": "vector", "shape_id": 2217},
            "debug": {},
        }
    ]
    document = {
        "format": "fls_editor_project",
        "version": 3,
        "name": "ChromaticMaskOracle",
        "car_id": 2017,
        "is_livery": True,
        "root": {"children": sections},
    }
    return gzip.compress(json.dumps(document, separators=(",", ":")).encode("utf-8"), mtime=0)


class FLSControlledPair4Tests(unittest.TestCase):
    def test_observed_fls_scene_maps_bgra_storage_to_semantic_rgba(self) -> None:
        artifact = load_fls_project_bytes(observed_chromatic_mask_project())
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.car_id, 2017)
        self.assertEqual(oracle.section_counts, (0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0))
        layer = oracle.layers[0]
        self.assertEqual(layer.section, "Top")
        self.assertEqual(layer.type_word, 2217)
        self.assertTrue(layer.mask)
        # Pair 5 screenshot later establishes FLS color lists as BGRA storage.
        self.assertEqual(layer.color_rgba, (0, 85, 255, 255))

    def test_real_controlled4_fls_clivery_pair_when_available(self) -> None:
        fls_value = os.environ.get("FH6_FLS_3SO_2017_CHROMATIC_MASK")
        clivery_value = os.environ.get("FH6_CLIVERY_2017_CHROMATIC_MASK")
        if (
            not fls_value
            or not clivery_value
            or not Path(fls_value).is_file()
            or not Path(clivery_value).is_file()
        ):
            self.skipTest(
                "set FH6_FLS_3SO_2017_CHROMATIC_MASK and FH6_CLIVERY_2017_CHROMATIC_MASK "
                "to the controlled chromatic-mask pair"
            )

        fls_path = Path(fls_value)
        clivery_path = Path(clivery_value)
        fls_raw = fls_path.read_bytes()
        clivery_raw = clivery_path.read_bytes()
        self.assertEqual(hashlib.sha256(fls_raw).hexdigest(), REAL4_FLS_SHA256)
        self.assertEqual(hashlib.sha256(clivery_raw).hexdigest(), REAL4_CLIVERY_SHA256)

        artifact = load_fls_project_bytes(fls_raw)
        self.assertEqual(artifact.uncompressed_sha256, REAL4_FLS_UNCOMPRESSED_SHA256)
        oracle = semantic_project_from_fls_artifact(artifact)
        self.assertEqual(oracle.section_counts, REAL4_SECTION_COUNTS)
        self.assertEqual(tuple(layer.type_word for layer in oracle.layers), REAL4_SHAPE_IDS)

        inflated, _container = inflate_clivery(clivery_raw)
        self.assertEqual(hashlib.sha256(inflated).hexdigest(), REAL4_CLIVERY_INFLATED_SHA256)
        self.assertEqual(inflated[315:317], bytes((0x55, 0x00)))
        self.assertEqual(inflated[318], 0x01)

        scene = decode_clivery_file(clivery_path)
        flattened = flatten_livery_scene(scene)
        report = compare_fls_project_to_flattened(oracle, flattened)
        self.assertTrue(report.match, report.to_dict())

        top = next(section for section in flattened.sections if section.name == "Top")
        self.assertEqual(top.flattened_count, 1)
        layer = top.layers[0]
        self.assertEqual(layer.type_word, 2217)
        self.assertEqual(layer.source_offset, 287)
        self.assertEqual(layer.color_rgba, (0, 85, 255, 255))
        self.assertTrue(layer.mask)
        self.assertEqual(layer.mask_evidence, ("section_terminal_state_01",))


if __name__ == "__main__":
    unittest.main()
