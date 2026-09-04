from __future__ import annotations

import struct
import unittest
from unittest.mock import patch

from fh6garage.preview3d import near_lod


class NearLodStructuralFallbackTests(unittest.TestCase):
    @staticmethod
    def scene_with_paths(*paths: str) -> dict:
        models = [{"resource_path": path} for path in paths]
        return {
            "standard_parts": [{"models": models[:1]}] if models else [],
            "upgradable_parts": [
                {
                    "upgrades": [{"legacy_models": models[1:2]}],
                    "shared_models": [{"model": model} for model in models[2:]],
                }
            ] if len(models) > 1 else [],
        }

    def test_structural_fallback_resolves_only_explicit_model_paths(self):
        archive_names = {
            "scene/body.modelbin": "scene/body.modelbin",
            "scene/bumper.modelbin": "scene/bumper.modelbin",
            "scene/shared.modelbin": "scene/shared.modelbin",
            "scene/unrelated.modelbin": "scene/unrelated.modelbin",
        }
        scene = self.scene_with_paths(
            "game:/media/cars/TEST/scene/body.modelbin",
            "game:/media/cars/TEST/scene/bumper.modelbin",
            "game:/media/cars/TEST/scene/shared.modelbin",
        )
        with patch.object(near_lod, "parse_fh6_carbin", return_value=scene):
            refs, discovered, unresolved = near_lod._referenced_model_paths(
                b"no raw game-backslash model paths here",
                archive_names,
                "TEST",
            )
        self.assertEqual(set(refs.values()), {
            "scene/body.modelbin",
            "scene/bumper.modelbin",
            "scene/shared.modelbin",
        })
        self.assertEqual(len(discovered), 3)
        self.assertEqual(unresolved, ())
        self.assertNotIn("scene/unrelated.modelbin", refs.values())

    def test_existing_raw_reference_path_does_not_require_structural_parser(self):
        archive_names = {"scene/body.modelbin": "scene/body.modelbin"}
        carbin = b"game:\\media\\cars\\TEST\\scene\\body.modelbin"
        with patch.object(near_lod, "parse_fh6_carbin", side_effect=AssertionError("must not run")):
            refs, discovered, unresolved = near_lod._referenced_model_paths(carbin, archive_names, "TEST")
        self.assertEqual(set(refs.values()), {"scene/body.modelbin"})
        self.assertEqual(len(discovered), 1)
        self.assertEqual(unresolved, ())

    def test_structural_fallback_keeps_fail_closed_when_scene_has_no_model_paths(self):
        with patch.object(near_lod, "parse_fh6_carbin", return_value={"standard_parts": [], "upgradable_parts": []}):
            refs, discovered, unresolved = near_lod._referenced_model_paths(b"no references", {}, "TEST")
        self.assertEqual(refs, {})
        self.assertEqual(discovered, ())
        self.assertEqual(unresolved, ())

    def test_structural_slod_rewrite_changes_only_selected_length_prefixed_path(self):
        selected_path = "game:/media/cars/TEST/scene/body__slod.modelbin"
        unrelated_path = "game:/media/cars/TEST/scene/unrelated__slod.modelbin"
        selected_raw = selected_path.encode("utf-8")
        unrelated_raw = unrelated_path.encode("utf-8")
        carbin = (
            b"prefix"
            + struct.pack("<i", len(selected_raw)) + selected_raw
            + b"middle"
            + struct.pack("<i", len(unrelated_raw)) + unrelated_raw
            + b"suffix"
        )
        scene = self.scene_with_paths(selected_path, unrelated_path)
        with patch.object(near_lod, "parse_fh6_carbin", return_value=scene):
            patched, count, entries = near_lod._rewrite_selected_slod_paths(
                carbin,
                {"scene/body__slod.modelbin"},
                "TEST",
            )
        self.assertEqual(count, 1)
        self.assertEqual(entries, {"scene/body__slod.modelbin"})
        self.assertIn(b"body__nlod.modelbin", patched)
        self.assertIn(b"unrelated__slod.modelbin", patched)


if __name__ == "__main__":
    unittest.main()
