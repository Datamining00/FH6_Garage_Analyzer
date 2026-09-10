from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fh6garage.preview3d import wheel_morph_helper as helper


class WheelMorphHelperTests(unittest.TestCase):
    def test_verified_helper_sha_matches_transform_chain_binary(self):
        self.assertEqual(
            helper.WHEEL_MORPH_HELPER_SHA256,
            "334aa812fff4107c8d1b6b54492383c69bbb8dbdfd2a1a5cda84e571ae28c8b5",
        )
        self.assertEqual(
            helper.WHEEL_MORPH_HELPER_REVISION,
            "kfps_6f53ca3_w3_p3f_material_shader_parameters_uv4_v15",
        )

    def test_missing_bundled_helper_returns_none(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / helper.WHEEL_MORPH_HELPER_FILENAME
            with patch.object(helper, "bundled_wheel_morph_helper_candidates", return_value=(missing,)):
                self.assertIsNone(helper.verified_bundled_wheel_morph_helper())

    def test_wrong_bundled_helper_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / helper.WHEEL_MORPH_HELPER_FILENAME
            candidate.write_bytes(b"not the verified converter")
            with patch.object(helper, "bundled_wheel_morph_helper_candidates", return_value=(candidate,)):
                with self.assertRaises(helper.WheelMorphHelperError):
                    helper.verified_bundled_wheel_morph_helper()

    def test_matching_hash_returns_resolved_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / helper.WHEEL_MORPH_HELPER_FILENAME
            payload = b"deterministic test helper"
            candidate.write_bytes(payload)
            expected = hashlib.sha256(payload).hexdigest()
            with (
                patch.object(helper, "WHEEL_MORPH_HELPER_SHA256", expected),
                patch.object(helper, "bundled_wheel_morph_helper_candidates", return_value=(candidate,)),
            ):
                self.assertEqual(helper.verified_bundled_wheel_morph_helper(), candidate.resolve())


if __name__ == "__main__":
    unittest.main()
