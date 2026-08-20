from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unittest

from fh6garage.fh6_clivery import decode_clivery_file


SAMPLE_3761_SHA256 = "565e75445c70501dc98c00cc76c1d162d703b1921fd55735fcccb857757dac18"
SAMPLE_2997_SHA256 = "677751360dba1a7fe6eead246236094836e9e1433709a0fd8dc5a1b2635f7ded"


def _sample_path(variable: str) -> Path | None:
    value = os.environ.get(variable)
    if not value:
        return None
    path = Path(value)
    return path if path.is_file() else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RealLiveryRegressionTests(unittest.TestCase):
    def test_car_3761_fluorite_ake_when_sample_is_available(self) -> None:
        path = _sample_path("FH6_CLIVERY_3761")
        if path is None:
            self.skipTest("set FH6_CLIVERY_3761 to the real C_livery sample")
        self.assertEqual(_sha256(path), SAMPLE_3761_SHA256)
        result = decode_clivery_file(path)
        self.assertEqual(result.car_id, 3761)
        self.assertEqual(result.gyvl_offset, 51)
        self.assertEqual(result.body_start, 72)
        self.assertEqual(result.body_end, 275791)
        self.assertEqual(
            [item.declared_count for item in result.sections],
            [1, 21, 2980, 2761, 2785, 3, 0, 0, 0, 18, 0],
        )

    def test_livery_2997_when_sample_is_available(self) -> None:
        path = _sample_path("FH6_CLIVERY_2997")
        if path is None:
            self.skipTest("set FH6_CLIVERY_2997 to the real Livery_2997_20260817150058 C_livery sample")
        self.assertEqual(_sha256(path), SAMPLE_2997_SHA256)
        result = decode_clivery_file(path)
        self.assertEqual(result.car_id, 2997)
        self.assertEqual(result.gyvl_offset, 51)
        self.assertEqual(result.body_start, 72)
        self.assertEqual(result.body_end, 293929)
        self.assertEqual(
            [item.declared_count for item in result.sections],
            [24, 156, 2894, 2989, 2964, 0, 18, 41, 0, 0, 0],
        )


if __name__ == "__main__":
    unittest.main()
