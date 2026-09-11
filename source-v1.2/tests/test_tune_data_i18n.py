from __future__ import annotations

import struct
import unittest

from fh6garage.i18n import DEFAULT_LANGUAGE, set_language, tune_label
from fh6garage.tune_data import EXPECTED_TUNE_DATA_SIZE, TuneDataError, parse_tune_data


class TuneDataI18nTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    @staticmethod
    def _blank_data() -> bytes:
        return bytes(EXPECTED_TUNE_DATA_SIZE)

    def test_korean_labels_remain_backward_compatible(self) -> None:
        set_language("ko")
        parsed = parse_tune_data(self._blank_data())
        self.assertEqual(parsed.parts[0][1], "엔진")
        self.assertEqual(parsed.parts[-1][1], "후륜 휠 스타일")
        self.assertEqual(parsed.values[0][1], "전륜 다운포스")
        self.assertEqual(parsed.values[-1][1], "10단 기어비")

    def test_english_labels_cover_parts_tuning_and_gears(self) -> None:
        set_language("en")
        parsed = parse_tune_data(self._blank_data())
        self.assertEqual(parsed.parts[0][1], "Engine")
        self.assertEqual(parsed.parts[-1][1], "Rear wheel style")
        self.assertEqual(parsed.values[0][1], "Front downforce")
        self.assertEqual(parsed.values[-1][1], "Gear 10 ratio")
        self.assertEqual(tune_label("전륜 안티롤바"), "Front anti-roll bar")

    def test_unknown_tune_label_falls_back_to_original_text(self) -> None:
        set_language("en")
        self.assertEqual(tune_label("알 수 없는 항목"), "알 수 없는 항목")

    def test_size_error_is_localized(self) -> None:
        set_language("ko")
        with self.assertRaisesRegex(TuneDataError, r"Data 파일 크기가 0바이트"):
            parse_tune_data(b"")

        set_language("en")
        with self.assertRaisesRegex(TuneDataError, r"Data file is 0 bytes; expected 598 bytes"):
            parse_tune_data(b"")

    def test_nonfinite_value_error_is_localized(self) -> None:
        data = bytearray(self._blank_data())
        struct.pack_into("<f", data, 0x019E, float("nan"))

        set_language("ko")
        with self.assertRaisesRegex(TuneDataError, "NaN 또는 무한대"):
            parse_tune_data(bytes(data))

        set_language("en")
        with self.assertRaisesRegex(TuneDataError, "NaN or infinite values"):
            parse_tune_data(bytes(data))


if __name__ == "__main__":
    unittest.main()
