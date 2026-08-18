from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from fh6garage.exact_livery_preview import (
    IndexedFH6RasterDecalResolver,
    _index_decal_members,
)
from fh6garage.livery_preview_preview2 import (
    PREVIEW2_CACHE_VERSION,
    QUALITY_DIMENSIONS,
    _projection_supersampled,
)


class RasterDecalIndexTests(unittest.TestCase):
    def test_numeric_index_accepts_case_padding_and_separator_variants(self) -> None:
        indexed = _index_decal_members(
            [
                "Textures/Decal0050.swatchbin",
                "textures/decal-51.SWATCHBIN",
                "textures/decal_00052.swatchbin",
                "textures/not-a-decal.swatchbin",
            ]
        )
        self.assertEqual(indexed[50], "Textures/Decal0050.swatchbin")
        self.assertEqual(indexed[51], "textures/decal-51.SWATCHBIN")
        self.assertEqual(indexed[52], "textures/decal_00052.swatchbin")

    def test_indexed_resolver_uses_actual_archive_member_instead_of_fixed_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "Decals.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Textures/Decal0050.swatchbin", b"fixture")

            raster_backend = SimpleNamespace(
                resolve_fh6_decals_archive=lambda _folder: archive,
                decode_fh6_decal_swatch=lambda data: ("decoded", data),
            )
            with patch(
                "fh6garage.exact_livery_preview._load_backend",
                return_value=(None, None, raster_backend),
            ):
                resolver = IndexedFH6RasterDecalResolver(root)
                self.assertEqual(resolver(50), ("decoded", b"fixture"))
                self.assertIsNone(resolver(49))
                self.assertIn("50", resolver.missing_description(49))


class SupersampledProjectionTests(unittest.TestCase):
    def test_quality_contract_matches_preview2_labels(self) -> None:
        self.assertEqual(QUALITY_DIMENSIONS["fast"], (2048, 1024, 1.0))
        self.assertEqual(QUALITY_DIMENSIONS["balanced"], (3072, 1536, 1.5))
        self.assertEqual(QUALITY_DIMENSIONS["high"], (4096, 2048, 2.0))
        self.assertIn("render-rules-r2", PREVIEW2_CACHE_VERSION)

    def test_projection_downsamples_only_after_scaled_warp_and_mask(self) -> None:
        class Contract:
            ATLAS_SIZE = (4, 2)

            @staticmethod
            def _atlas_to_local_affine(_slot, _width, _height, _xorigin, _yorigin):
                return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

            @staticmethod
            def _projection_pixel_bounds(_projection):
                return (0, 0, 4, 2)

            @staticmethod
            def _masked_atlas_layer(artwork, mask, _slot, _projection):
                rgba = artwork.copy()
                rgba.putalpha(mask)
                return rgba

        source = Image.new("RGBA", (8, 4), (0, 0, 0, 0))
        for x in range(4):
            for y in range(4):
                source.putpixel((x, y), (255, 0, 0, 255))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")
        mask = Image.new("L", (4, 2), 255)

        with patch(
            "fh6garage.livery_preview_preview2._projection_record",
            return_value=(Contract, "left", mask, {"xorigin": "0", "yorigin": "0"}, "hash"),
        ):
            result = _projection_supersampled(
                buffer.getvalue(),
                "Left",
                1,
                game_folder=Path("."),
                scale=2.0,
            )

        with Image.open(io.BytesIO(result)) as rendered:
            self.assertEqual(rendered.size, (4, 2))
            self.assertEqual(rendered.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
