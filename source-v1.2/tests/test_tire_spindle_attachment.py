from __future__ import annotations

import unittest

from fh6garage.preview3d.tire_spindle_attachment import (
    TireSpindleAttachmentError,
    resolve_tire_spindle_attachment_contract,
)


def _matrix(seed: float) -> list[float]:
    values = [0.0] * 16
    values[0] = 1.0
    values[5] = 1.0
    values[10] = 1.0
    values[15] = 1.0
    values[12] = seed
    values[13] = seed + 1.0
    values[14] = seed + 2.0
    return values


def _model(bone: str, seed: float) -> dict:
    return {
        "bone_name": bone,
        "resource_path": f"media/cars/_library/scene/tires/{bone}.modelbin",
        "transform_matrix_row_major": _matrix(seed),
    }


def _parsed_standard() -> dict:
    return {
        "scene": {"ordinal": 1006},
        "tire_related_parts": [
            {
                "kind": "standard",
                "resolved_part_type": 8,
                "models": [
                    _model("spindleLF", 1.0),
                    _model("spindleRF", 2.0),
                    _model("spindleLR", 3.0),
                    _model("spindleRR", 4.0),
                ],
            }
        ],
    }


def _trial() -> dict:
    return {
        "format": "fh6_native_tire_production_trial_geometry_v1",
        "status": "production_trial_geometry_ready",
        "car_id": 1006,
        "trial_renderer_input_ready": True,
        "production_renderer_enabled": False,
        "front": {
            "modelbins": [
                {"entry": "tirel_slick.modelbin", "glb_path": "front_left.glb"},
                {"entry": "tireR_slick.modelbin", "glb_path": "front_right.glb"},
            ]
        },
        "rear": {
            "modelbins": [
                {"entry": "tirel_slick.modelbin", "glb_path": "rear_left.glb"},
                {"entry": "tireR_slick.modelbin", "glb_path": "rear_right.glb"},
            ]
        },
    }


class TireSpindleAttachmentTests(unittest.TestCase):
    def test_exact_four_spindles_preserve_native_matrices(self) -> None:
        parsed = _parsed_standard()
        contract = resolve_tire_spindle_attachment_contract(parsed, _trial())

        self.assertEqual(contract.status, "spindle_attachment_contract_ready")
        self.assertTrue(contract.native_carbin_transform_only)
        self.assertFalse(contract.procedural_translation_applied)
        self.assertFalse(contract.procedural_rotation_applied)
        self.assertFalse(contract.procedural_scale_applied)
        self.assertTrue(contract.spindle_attachment_contract_ready)
        self.assertFalse(contract.spindle_attachment_applied)
        self.assertFalse(contract.production_renderer_enabled)
        self.assertEqual(
            [(item.spindle_bone, item.axle, item.side) for item in contract.attachments],
            [
                ("spindleLF", "front", "left"),
                ("spindleRF", "front", "right"),
                ("spindleLR", "rear", "left"),
                ("spindleRR", "rear", "right"),
            ],
        )
        self.assertEqual(
            contract.attachments[0].carbin_transform_matrix_row_major,
            tuple(_matrix(1.0)),
        )
        self.assertEqual(contract.attachments[0].derived_tire_glb_path, "front_left.glb")
        self.assertEqual(contract.attachments[3].derived_tire_glb_path, "rear_right.glb")

    def test_upgradable_tirecompound_uses_only_stock_shared_models(self) -> None:
        parsed = {
            "scene": {"ordinal": 1006},
            "tire_related_parts": [
                {
                    "kind": "upgradable",
                    "resolved_part_type": 8,
                    "upgrades": [
                        {"is_stock": True, "part_id": 13, "legacy_models": []},
                        {"is_stock": False, "part_id": 99, "legacy_models": []},
                    ],
                    "shared_models": [
                        {"upgrade_ids": [13], "model": _model("spindleLF", 1.0)},
                        {"upgrade_ids": [13], "model": _model("spindleRF", 2.0)},
                        {"upgrade_ids": [13], "model": _model("spindleLR", 3.0)},
                        {"upgrade_ids": [13], "model": _model("spindleRR", 4.0)},
                        {"upgrade_ids": [99], "model": _model("spindleLF", 9.0)},
                    ],
                }
            ],
        }
        contract = resolve_tire_spindle_attachment_contract(parsed, _trial())
        self.assertEqual(len(contract.attachments), 4)
        self.assertEqual(
            contract.attachments[0].carbin_transform_matrix_row_major,
            tuple(_matrix(1.0)),
        )

    def test_tire_width_part_is_not_used_as_slick_attachment_source(self) -> None:
        parsed = {
            "scene": {"ordinal": 1006},
            "tire_related_parts": [
                {
                    "kind": "standard",
                    "resolved_part_type": 38,
                    "models": [
                        _model("spindleLF", 1.0),
                        _model("spindleRF", 2.0),
                        _model("spindleLR", 3.0),
                        _model("spindleRR", 4.0),
                    ],
                }
            ],
        }
        with self.assertRaisesRegex(TireSpindleAttachmentError, "missing exact native spindle"):
            resolve_tire_spindle_attachment_contract(parsed, _trial())

    def test_missing_spindle_fails_closed(self) -> None:
        parsed = _parsed_standard()
        parsed["tire_related_parts"][0]["models"].pop()
        with self.assertRaisesRegex(TireSpindleAttachmentError, "spindleRR"):
            resolve_tire_spindle_attachment_contract(parsed, _trial())

    def test_duplicate_spindle_fails_closed(self) -> None:
        parsed = _parsed_standard()
        parsed["tire_related_parts"][0]["models"].append(_model("spindleLF", 9.0))
        with self.assertRaisesRegex(TireSpindleAttachmentError, "ambiguous duplicate"):
            resolve_tire_spindle_attachment_contract(parsed, _trial())

    def test_car_id_mismatch_fails_closed(self) -> None:
        trial = _trial()
        trial["car_id"] = 1229
        with self.assertRaisesRegex(TireSpindleAttachmentError, "Car ID mismatch"):
            resolve_tire_spindle_attachment_contract(_parsed_standard(), trial)

    def test_unknown_modelbin_side_fails_closed(self) -> None:
        trial = _trial()
        trial["front"]["modelbins"][0]["entry"] = "tire_slick.modelbin"
        with self.assertRaisesRegex(TireSpindleAttachmentError, "tireL_/tireR_"):
            resolve_tire_spindle_attachment_contract(_parsed_standard(), trial)

    def test_missing_derived_glb_fails_closed(self) -> None:
        trial = _trial()
        trial["rear"]["modelbins"][1]["glb_path"] = None
        with self.assertRaisesRegex(TireSpindleAttachmentError, "no derived GLB path"):
            resolve_tire_spindle_attachment_contract(_parsed_standard(), trial)

    def test_nonfinite_native_matrix_fails_closed(self) -> None:
        parsed = _parsed_standard()
        parsed["tire_related_parts"][0]["models"][0]["transform_matrix_row_major"][3] = float("nan")
        with self.assertRaisesRegex(TireSpindleAttachmentError, "non-finite"):
            resolve_tire_spindle_attachment_contract(parsed, _trial())


if __name__ == "__main__":
    unittest.main()
