from __future__ import annotations

import unittest

from fh6garage.preview3d.part_visibility_patch import classify_part_group


class PartVisibilityPatchTests(unittest.TestCase):
    def test_wheel_and_tire_groups_use_structured_or_tokenized_identity(self):
        self.assertEqual(classify_part_group({"part_type": "WheelStyle"}), "wheel_tire")
        self.assertEqual(classify_part_group({"part_type": "Tire"}), "wheel_tire")
        self.assertEqual(classify_part_group({"source_entry": "Scene/Exterior/Tires/tireLF.modelbin"}), "wheel_tire")
        self.assertEqual(classify_part_group({"fh6_native_tire_trial": True}), "wheel_tire")

    def test_primary_lights_do_not_match_rim_substring(self):
        self.assertEqual(
            classify_part_group({"source_entry": "Scene/Exterior/PrimaryLights/glassLHL.modelbin"}),
            "other",
        )

    def test_brake_and_disc_join_other_mechanical(self):
        self.assertEqual(classify_part_group({"part_type": "Brakes"}), "other_mechanical")
        self.assertEqual(classify_part_group({"mesh_name": "front_brake_rotor"}), "other_mechanical")

    def test_underbody_joins_other_mechanical(self):
        self.assertEqual(classify_part_group({"mesh_name": "suspension_controlArmLF"}), "other_mechanical")
        self.assertEqual(
            classify_part_group({"source_entry": "Scene/Exterior/Chassis/axleRear.modelbin"}),
            "other_mechanical",
        )

    def test_body_panel_is_not_hidden(self):
        self.assertEqual(classify_part_group({"part_type": "CarBody", "mesh_name": "doorLF"}), "other")


if __name__ == "__main__":
    unittest.main()
