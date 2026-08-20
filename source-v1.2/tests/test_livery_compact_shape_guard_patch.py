from __future__ import annotations

import unittest

from fh6garage.livery_compact_shape_guard_patch import (
    _compact_shape_word,
    _guarded_is_valid_shape_at,
)


class _Renderer:
    def __init__(self, accepted_words=()):
        self.accepted_words = {int(word) & 0xFFFF for word in accepted_words}

    def _resolve_vinyl_resource(self, type_code, shape):
        word = int(shape.get("shape_word", type_code)) & 0xFFFF
        if word in self.accepted_words:
            return ("Primitives", 1)
        return None


class CompactShapeGuardTests(unittest.TestCase):
    def test_unresolved_compact_0100_is_rejected(self):
        # Exact 31-byte record pattern captured from the supplied FH6 C_livery.
        # The upstream numeric plausibility test can treat this as a shape even
        # though 0x0100 has no pinned native resource identity.
        body = bytes.fromhex(
            "02 00 01 00 00 00 01 48 1e a7 3f 68 eb 7b 3f "
            "74 66 e6 3e 00 00 00 c1 20 04 00 01 00 00 00 0f"
        )
        self.assertEqual(_compact_shape_word(body, 0, len(body)), 0x0100)
        self.assertFalse(
            _guarded_is_valid_shape_at(lambda *_args: True, _Renderer(), body, 0, len(body))
        )

    def test_resolved_compact_word_is_preserved(self):
        body = bytes.fromhex(
            "02 88 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
        )
        self.assertEqual(_compact_shape_word(body, 0, len(body)), 0x0088)
        self.assertTrue(
            _guarded_is_valid_shape_at(
                lambda *_args: True,
                _Renderer({0x0088}),
                body,
                0,
                len(body),
            )
        )

    def test_explicit_00_02_record_is_not_restricted(self):
        body = bytes.fromhex(
            "00 02 00 01" + " 00" * 28
        )
        self.assertIsNone(_compact_shape_word(body, 0, len(body)))
        self.assertTrue(
            _guarded_is_valid_shape_at(lambda *_args: True, _Renderer(), body, 0, len(body))
        )

    def test_upstream_rejection_stays_rejected(self):
        body = b"\x02" + (b"\x00" * 30)
        self.assertFalse(
            _guarded_is_valid_shape_at(lambda *_args: False, _Renderer({0}), body, 0, len(body))
        )


if __name__ == "__main__":
    unittest.main()
