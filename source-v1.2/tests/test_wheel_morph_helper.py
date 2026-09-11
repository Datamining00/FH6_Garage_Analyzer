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
            "3c90cc38a939bb91f7fb3ef71c8330c1665a18708be1b9e4018b01402adb5411",
        )
        self.assertEqual(
            helper.WHEEL_MORPH_HELPER_REVISION,
            "kfps_6f53ca3_w3_p3f_material_shader_parameters_uv4_durango_guard_v16",
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

    def test_release_specs_bundle_native_tire_preview_cache_patch(self):
        source_root = Path(__file__).resolve().parents[1]
        required = "'fh6garage.preview3d.tire_preview_cache_patch'"
        for spec_name in ("FH6_Assistant_v1.4.spec", "FH6_Assistant_v1.4_portable.spec"):
            spec_text = (source_root / spec_name).read_text(encoding="utf-8")
            self.assertIn(
                required,
                spec_text,
                msg=f"{spec_name} must explicitly bundle the lazy native tire preview cache patch",
            )


if __name__ == "__main__":
    unittest.main()
