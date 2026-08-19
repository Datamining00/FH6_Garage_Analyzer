from __future__ import annotations

import unittest

from fh6garage.livery_analysis import LIVERY_SECTION_NAMES
from fh6garage.livery_render_integrity_patch import _integrity_failure_for_section


def _counts(**overrides):
    values = {name: 0 for name in LIVERY_SECTION_NAMES}
    values.update({key: int(value) for key, value in overrides.items()})
    return values


def _sections(**sizes):
    result = {name: tuple() for name in LIVERY_SECTION_NAMES}
    for name, size in sizes.items():
        result[name] = tuple({"source_section": name} for _ in range(int(size)))
    return result


class LiveryRenderIntegrityTests(unittest.TestCase):
    def test_direct_mismatch_blocks_requested_section(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Left=3000),
            _sections(Left=2991),
            "Left",
        )
        self.assertEqual(failure, ("Left", 3000, 2991, False))

    def test_previous_mismatch_blocks_later_section_even_when_later_count_matches(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Left=3000, Right=3000),
            _sections(Left=2991, Right=3000),
            "Right",
        )
        self.assertEqual(failure, ("Left", 3000, 2991, True))

    def test_later_mismatch_does_not_block_earlier_verified_section(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Top=10, Left=3000),
            _sections(Top=10, Left=2991),
            "Top",
        )
        self.assertIsNone(failure)

    def test_recovered_exact_counts_allow_later_section(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Left=3000, Right=3000),
            _sections(Left=3000, Right=3000),
            "Right",
        )
        self.assertIsNone(failure)


if __name__ == "__main__":
    unittest.main()
