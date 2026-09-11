from __future__ import annotations

import unittest

from fh6garage.preview3d.glb_parser import _structural_livery_exclusion_reason


class StructuralLiveryExclusionTests(unittest.TestCase):
    def test_brakes_are_excluded(self):
        self.assertEqual(
            _structural_livery_exclusion_reason({"kfps_part_type": "Brakes"}),
            "part_type_brakes",
        )

    def test_wheelstyle_is_excluded(self):
        self.assertEqual(
            _structural_livery_exclusion_reason({"kfps_part_type": "WheelStyle"}),
            "part_type_wheelstyle",
        )

    def test_scene_interior_is_excluded(self):
        self.assertEqual(
            _structural_livery_exclusion_reason(
                {"kfps_source_entry": r"Scene\Interior\Dash\dash_a.modelbin"}
            ),
            "scene_interior",
        )

    def test_exterior_door_jamb_is_excluded(self):
        self.assertEqual(
            _structural_livery_exclusion_reason(
                {
                    "kfps_part_type": "CarBody",
                    "kfps_source_entry": r"Scene\Exterior\Doors\doorJambLF_a.modelbin",
                }
            ),
            "exterior_door_jamb",
        )

    def test_exterior_door_sill_is_excluded(self):
        self.assertEqual(
            _structural_livery_exclusion_reason(
                {
                    "kfps_part_type": "CarBody",
                    "kfps_source_entry": r"Scene\Exterior\Platform\doorSill_a.modelbin",
                }
            ),
            "exterior_door_sill",
        )

    def test_normal_exterior_door_remains_eligible(self):
        self.assertEqual(
            _structural_livery_exclusion_reason(
                {
                    "kfps_part_type": "CarBody",
                    "kfps_source_entry": r"Scene\Exterior\Doors\doorLF_a.modelbin",
                }
            ),
            "",
        )

    def test_hood_and_bumper_remain_eligible(self):
        for source in (
            r"Scene\Exterior\Hood\hood_a.modelbin",
            r"Scene\Exterior\Bumpers\bumperF_a.modelbin",
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    _structural_livery_exclusion_reason(
                        {"kfps_part_type": "CarBody", "kfps_source_entry": source}
                    ),
                    "",
                )


if __name__ == "__main__":
    unittest.main()
