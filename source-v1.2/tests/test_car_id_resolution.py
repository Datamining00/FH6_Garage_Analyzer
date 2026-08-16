from __future__ import annotations

import unittest

from fh6garage.scanner import _container_car_id, _resolve_car_id


class _FakeCarDatabase:
    def __init__(self, known: set[int]):
        self.known = known

    def is_known(self, car_id: int) -> bool:
        return car_id in self.known


class CarIdResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        # 1229 = 2008 Mazda Furai in the bundled FH6 CarOrdinal database.
        self.db = _FakeCarDatabase({1229, 343})

    def test_extracts_carordinal_from_livery_container_name(self) -> None:
        self.assertEqual(
            _container_car_id("Livery_1229_20260816092247", "Livery"),
            1229,
        )

    def test_furai_sample_one_recovers_from_invalid_header_tail(self) -> None:
        self.assertEqual(
            _resolve_car_id(
                "Livery_1229_20260816092247",
                "Livery",
                1091571919,
                self.db,
            ),
            1229,
        )

    def test_furai_sample_two_recovers_from_invalid_header_tail(self) -> None:
        self.assertEqual(
            _resolve_car_id(
                "Livery_1229_20260816092257",
                "Livery",
                2547241910,
                self.db,
            ),
            1229,
        )

    def test_legacy_result_is_unchanged_when_container_name_has_no_ordinal(self) -> None:
        self.assertEqual(
            _resolve_car_id("Livery_unknown", "Livery", 343, self.db),
            343,
        )

    def test_kind_mismatch_does_not_override_header(self) -> None:
        self.assertEqual(
            _resolve_car_id("Tuning_1229_123", "Livery", 343, self.db),
            343,
        )

    def test_unknown_container_ordinal_does_not_replace_known_header(self) -> None:
        self.assertEqual(
            _resolve_car_id("Livery_999999_123", "Livery", 343, self.db),
            343,
        )


if __name__ == "__main__":
    unittest.main()
