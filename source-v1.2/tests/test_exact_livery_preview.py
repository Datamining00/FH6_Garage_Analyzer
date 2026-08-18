from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageChops

from fh6garage.exact_livery_preview import (
    apply_exact_vehicle_projection,
    clear_exact_preview_cache,
    configured_fh6_game_folder,
    set_fh6_game_folder,
)


class _FakeVehicleAssets:
    @staticmethod
    def normalize_fh6_game_folder(path):
        path = Path(path)
        if path.name == "bad":
            raise RuntimeError("bad folder")
        return path

    @staticmethod
    def discover_fh6_game_folder():
        return None

    @staticmethod
    def load_or_build_vehicle_asset_index(game_folder, cache_path):
        return {3650: SimpleNamespace(car_id=3650, archive_name="amg-one.zip")}


class _FakeRasterDecals:
    class FH6RasterDecalResolver:
        def __init__(self, game_folder):
            self.game_folder = str(game_folder)


class _FakeRenderContract:
    ATLAS_SIZE = (64, 32)
    SECTION_TO_SLOT = {"Left": "left"}

    @staticmethod
    def _archive_masks(asset):
        mask = Image.new("L", (64, 32), 0)
        for x in range(12, 52):
            for y in range(6, 26):
                mask.putpixel((x, y), 255)
        projection = {
            "left": -32,
            "right": 32,
            "top": 16,
            "bottom": -16,
        }
        return {"left": (mask, projection, "fake-hash")}

    @staticmethod
    def _masked_atlas_layer(artwork, mask, slot, projection):
        result = artwork.copy()
        result.putalpha(ImageChops.multiply(result.getchannel("A"), mask))
        return result

    @staticmethod
    def _projection_pixel_bounds(projection):
        return (0, 0, 64, 32)


def _fake_backend():
    return _FakeVehicleAssets, _FakeRenderContract, _FakeRasterDecals


class ExactLiveryPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_exact_preview_cache()

    def tearDown(self) -> None:
        clear_exact_preview_cache()

    def test_selected_game_folder_is_persisted_and_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local = Path(temp_dir) / "local"
            game = Path(temp_dir) / "FH6" / "Content"
            game.mkdir(parents=True)
            with patch.dict("os.environ", {"LOCALAPPDATA": str(local), "FH6_GAME_FOLDER": ""}, clear=False), patch(
                "fh6garage.exact_livery_preview._load_backend", side_effect=_fake_backend
            ):
                selected = set_fh6_game_folder(game)
                clear_exact_preview_cache()
                resolved = configured_fh6_game_folder()

        self.assertEqual(selected, game.resolve())
        self.assertEqual(resolved, game.resolve())

    def test_configured_path_lookup_does_not_load_or_discover_game_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local = Path(temp_dir) / "local"
            game = Path(temp_dir) / "FH6" / "Content"
            game.mkdir(parents=True)
            preference = local / "FH6GarageAnalyzer" / "fh6_game_folder.txt"
            preference.parent.mkdir(parents=True)
            preference.write_text(str(game), encoding="utf-8")

            with patch.dict(
                "os.environ",
                {"LOCALAPPDATA": str(local), "FH6_GAME_FOLDER": ""},
                clear=False,
            ), patch("fh6garage.exact_livery_preview._load_backend") as backend:
                resolved = configured_fh6_game_folder()
                backend.assert_not_called()

        self.assertEqual(resolved, game)

    def test_exact_projection_clips_artwork_to_vehicle_mask(self) -> None:
        artwork = Image.new("RGBA", (64, 32), (220, 80, 100, 255))
        source = io.BytesIO()
        artwork.save(source, format="PNG")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "fh6garage.exact_livery_preview._load_backend", side_effect=_fake_backend
        ):
            output = apply_exact_vehicle_projection(
                source.getvalue(),
                "Left",
                3650,
                game_folder=Path(temp_dir),
            )

        with Image.open(io.BytesIO(output)) as image:
            alpha = image.convert("RGBA").getchannel("A")
            self.assertEqual(alpha.getpixel((0, 0)), 0)
            self.assertGreater(alpha.getpixel((20, 10)), 0)
            self.assertEqual(alpha.getpixel((63, 31)), 0)


if __name__ == "__main__":
    unittest.main()
