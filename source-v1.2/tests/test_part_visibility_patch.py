from __future__ import annotations

import unittest

from fh6garage.preview3d.part_visibility_patch import classify_part_group


class PartVisibilityPatchTests(unittest.TestCase):
    def test_wheel_and_tire_groups(self):
        self.assertEqual(classify_part_group({"part_type": "WheelStyle"}), "wheel_tire")
        self.assertEqual(classify_part_group({"source_entry": "Scene/Exterior/Tires/tireLF.modelbin"}), "wheel_tire")

    def test_brake_and_disc_groups(self):
        self.assertEqual(classify_part_group({"part_type": "Brakes"}), "brake")
        self.assertEqual(classify_part_group({"mesh_name": "front_brake_rotor"}), "brake")

    def test_underbody_groups(self):
        self.assertEqual(classify_part_group({"mesh_name": "suspension_controlArmLF"}), "underbody")
        self.assertEqual(classify_part_group({"source_entry": "Scene/Exterior/Chassis/axleRear.modelbin"}), "underbody")

    def test_body_panel_is_not_hidden(self):
        self.assertEqual(classify_part_group({"part_type": "CarBody", "mesh_name": "doorLF"}), "other")


if __name__ == "__main__":
    unittest.main()
