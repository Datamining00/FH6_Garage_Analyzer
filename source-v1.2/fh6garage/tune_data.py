from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from pathlib import Path

from .i18n import tr, tune_label


EXPECTED_TUNE_DATA_SIZE = 598


class TuneDataError(ValueError):
    pass


PART_FIELDS: tuple[tuple[int, str], ...] = (
    (0x000E, "엔진"), (0x0012, "구동계"), (0x0016, "차체"),
    (0x001A, "모터"), (0x001E, "브레이크"), (0x0022, "스프링·댐퍼"),
    (0x0026, "전륜 안티롤바"), (0x002A, "후륜 안티롤바"),
    (0x002E, "타이어 컴파운드"), (0x0032, "리어 윙"),
    (0x0036, "전륜 휠 크기"), (0x003A, "후륜 휠 크기"),
    (0x003E, "캠축"), (0x0042, "밸브"), (0x0046, "배기량"),
    (0x004A, "피스톤·압축"), (0x004E, "연료 시스템"),
    (0x0052, "점화"), (0x0056, "배기"), (0x005A, "흡기"),
    (0x005E, "플라이휠"), (0x0062, "매니폴드"),
    (0x0066, "리스트릭터 플레이트"), (0x006A, "오일 냉각"),
    (0x006E, "싱글 터보"), (0x0072, "트윈 터보"),
    (0x0076, "쿼드 터보"), (0x007A, "용적식 슈퍼차저"),
    (0x007E, "원심식 슈퍼차저"), (0x0082, "인터쿨러"),
    (0x0086, "클러치"), (0x008A, "변속기"),
    (0x008E, "드라이브라인"), (0x0092, "디퍼렌셜"),
    (0x0096, "전면 범퍼"), (0x009A, "후면 범퍼"),
    (0x009E, "보닛"), (0x00A2, "사이드 스커트"),
    (0x00A6, "전륜 타이어 폭"), (0x00AA, "후륜 타이어 폭"),
    (0x00AE, "경량화"), (0x00B2, "차체 보강·롤케이지"),
    (0x00B6, "모터 부품"), (0x00BA, "휠 스타일"),
    (0x00BE, "과급 방식"), (0x00C2, "전륜 트랙 폭"),
    (0x00C6, "후륜 트랙 폭"), (0x00CA, "전륜 타이어 편평비"),
    (0x00CE, "후륜 타이어 편평비"), (0x00D2, "후륜 휠 스타일"),
)

TUNE_FIELDS: tuple[tuple[int, str], ...] = (
    (0x019E, "전륜 다운포스"), (0x01A2, "후륜 다운포스"),
    (0x01A6, "최종감속비"), (0x01AA, "브레이크 압력"),
    (0x01AE, "브레이크 밸런스"), (0x01B2, "핸드브레이크 압력"),
    (0x01B6, "센터 디퍼렌셜"), (0x01C2, "TCS 슬립 기준"),
    (0x01CE, "전륜 공기압"), (0x01D2, "전륜 캠버"),
    (0x01D6, "전륜 토"), (0x01DA, "전륜 캐스터"),
    (0x01DE, "전륜 스프링"), (0x01E2, "전륜 안티롤바"),
    (0x01E6, "전륜 차고"), (0x01EA, "전륜 범프 강성"),
    (0x01EE, "전륜 리바운드 강성"), (0x01F2, "전륜 디퍼렌셜 가속"),
    (0x01F6, "전륜 디퍼렌셜 감속"), (0x01FA, "후륜 공기압"),
    (0x01FE, "후륜 캠버"), (0x0202, "후륜 토"),
    (0x0206, "후륜 캐스터"), (0x020A, "후륜 스프링"),
    (0x020E, "후륜 안티롤바"), (0x0212, "후륜 차고"),
    (0x0216, "후륜 범프 강성"), (0x021A, "후륜 리바운드 강성"),
    (0x021E, "후륜 디퍼렌셜 가속"), (0x0222, "후륜 디퍼렌셜 감속"),
    *tuple((0x022E + 4 * index, f"{index + 1}단 기어비") for index in range(10)),
)


@dataclass(frozen=True)
class ParsedTuneData:
    format_version: int
    locked: bool
    car_ordinal_id: int
    parts: tuple[tuple[int, str, int], ...]
    values: tuple[tuple[int, str, float], ...]


def parse_tune_data(data: bytes) -> ParsedTuneData:
    if len(data) != EXPECTED_TUNE_DATA_SIZE:
        raise TuneDataError(
            tr(
                "tune_data.size_error",
                actual=len(data),
                expected=EXPECTED_TUNE_DATA_SIZE,
            )
        )
    parts = tuple(
        (offset, tune_label(label), struct.unpack_from("<I", data, offset)[0])
        for offset, label in PART_FIELDS
    )
    values = tuple(
        (offset, tune_label(label), struct.unpack_from("<f", data, offset)[0])
        for offset, label in TUNE_FIELDS
    )
    if any(not math.isfinite(value) for _offset, _label, value in values):
        raise TuneDataError(tr("tune_data.nonfinite_error"))
    return ParsedTuneData(
        format_version=data[0],
        locked=bool(data[1]),
        car_ordinal_id=struct.unpack_from("<H", data, 2)[0],
        parts=parts,
        values=values,
    )


def read_tune_data(path: Path) -> ParsedTuneData:
    try:
        return parse_tune_data(path.read_bytes())
    except OSError as exc:
        raise TuneDataError(str(exc)) from exc
