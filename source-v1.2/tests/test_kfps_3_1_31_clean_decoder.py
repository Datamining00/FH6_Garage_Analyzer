from __future__ import annotations

import struct
import unittest
from pathlib import Path

from fh6garage import livery_baseline_behavior_patch as baseline_behavior
from fh6garage.livery_preview import _load_backend


ROOT = Path(__file__).resolve().parents[1]


class Kfps3131CleanDecoderTests(unittest.TestCase):
    def test_app_does_not_install_legacy_decoder_patches(self) -> None:
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        forbidden_calls = (
            "apply_livery_compact_shape_guard_patch()",
            "apply_livery_section_boundary_fix_patch()",
            "apply_livery_decoder_recovery_patch()",
            "apply_livery_bare_parent_transform_fix()",
            "apply_livery_consecutive_transform_pair_fix()",
            "install_livery_structural_parser_audit()",
            "apply_livery_baseline_behavior_patch()",
        )
        for call in forbidden_calls:
            self.assertNotIn(call, app)
        self.assertIn("apply_kfps_3_1_31_clean_baseline()", app)

    def test_clean_baseline_uses_existing_scale_persistence_installer(self) -> None:
        wrapper = (
            ROOT / "fh6garage" / "livery_kfps_3_1_31_clean_baseline.py"
        ).read_text(encoding="utf-8")
        self.assertTrue(
            hasattr(baseline_behavior, "_install_scale_persistence_and_warning_ui")
        )
        self.assertIn(
            "baseline._install_scale_persistence_and_warning_ui()",
            wrapper,
        )
        self.assertNotIn("baseline._install_scale_persistence()", wrapper)

    def test_backend_has_3_1_31_group_occupancy_model(self) -> None:
        decoder, _renderer = _load_backend()
        node = decoder.GroupNode()
        self.assertTrue(hasattr(node, "skipped_children"))
        self.assertTrue(hasattr(decoder, "is_unsupported_shape_record_at"))

    def test_unknown_framed_word_0100_is_not_a_native_shape(self) -> None:
        decoder, _renderer = _load_backend()
        record = (
            b"\x00\x02"
            + struct.pack("<Hffffff", 0x0100, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0)
            + bytes((0, 0, 0, 255))
        )
        self.assertEqual(len(record), 32)
        self.assertFalse(decoder.is_valid_shape_at(record, 0, len(record)))


if __name__ == "__main__":
    unittest.main()
