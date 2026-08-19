from __future__ import annotations

import unittest
from unittest.mock import patch

from fh6garage.livery_tiled_runtime_patch import _has_native_renderer_contract


class _ProjectionOnly:
    @staticmethod
    def _atlas_to_local_affine(*args, **kwargs):
        return (1, 0, 0, 0, 1, 0)


class _Native:
    @staticmethod
    def _shape_mask_flag(*args, **kwargs):
        return False

    @staticmethod
    def _resolve_vinyl_resource(*args, **kwargs):
        return None

    @staticmethod
    def _resource_alpha_triangles(*args, **kwargs):
        return None

    @staticmethod
    def _transform_resource_polygon(*args, **kwargs):
        return []


class TiledRuntimePatchTests(unittest.TestCase):
    def test_projection_contract_is_not_mistaken_for_native_renderer(self) -> None:
        self.assertFalse(_has_native_renderer_contract(_ProjectionOnly))

    def test_actual_native_renderer_contract_is_recognized(self) -> None:
        self.assertTrue(_has_native_renderer_contract(_Native))


if __name__ == "__main__":
    unittest.main()
