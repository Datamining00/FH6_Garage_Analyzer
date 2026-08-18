from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


LIVERY_SECTION_NAMES = (
    "Front",
    "Back",
    "Top",
    "Left",
    "Right",
    "Spoiler",
    "FrontWindshield",
    "BackWindshield",
    "TopWindow",
    "LeftWindow",
    "RightWindow",
)


class LiveryAnalysisError(ValueError):
    """Raised when a C_livery file cannot be decoded safely."""


@dataclass(frozen=True, slots=True)
class LiveryAnalysis:
    section_counts: dict[str, int]
    total_placements: int
    populated_sections: int
    payload_size: int
    gyvl_offset: int
    yrvl_offset: int


def unwrap_forza_container_bytes(raw: bytes) -> bytes:
    """Return the uncompressed FH6 payload without modifying the source file.

    FH6 save artifacts may either already contain the raw ``vlrc``/``gyvl``
    payload or consist of one or more zlib-compressed blocks.  Each compressed
    block starts with two little-endian uint32 values: compressed size and
    expected uncompressed size.
    """
    if raw.startswith((b"vlrc", b"gyvl")):
        return raw
    if len(raw) < 8:
        raise LiveryAnalysisError("C_livery 파일이 너무 짧습니다.")

    pos = 0
    payloads: list[bytes] = []
    while pos < len(raw):
        if pos + 8 > len(raw):
            raise LiveryAnalysisError(
                f"압축 블록 헤더가 잘렸습니다. (offset 0x{pos:X})"
            )
        compressed_len, payload_len = struct.unpack_from("<II", raw, pos)
        pos += 8
        remaining = len(raw) - pos
        if compressed_len <= 0 or compressed_len > remaining:
            raise LiveryAnalysisError(
                f"압축 블록 크기가 올바르지 않습니다. (offset 0x{pos - 8:X})"
            )
        compressed = raw[pos : pos + compressed_len]
        pos += compressed_len
        try:
            payload = zlib.decompress(compressed)
        except zlib.error as exc:
            raise LiveryAnalysisError(f"C_livery 압축 해제에 실패했습니다: {exc}") from exc
        if len(payload) != payload_len:
            raise LiveryAnalysisError(
                "압축 해제 크기가 파일 헤더와 일치하지 않습니다. "
                f"({len(payload)} != {payload_len})"
            )
        payloads.append(payload)

    if not payloads:
        raise LiveryAnalysisError("C_livery에서 압축 데이터를 찾지 못했습니다.")
    return b"".join(payloads)


def analyze_livery_bytes(raw: bytes) -> LiveryAnalysis:
    """Read the eleven FH6 livery projection-section placement counts."""
    payload = unwrap_forza_container_bytes(raw)

    gyvl = payload.find(b"gyvl")
    if gyvl < 0:
        raise LiveryAnalysisError("C_livery 내부에서 gyvl 리버리 블록을 찾지 못했습니다.")

    yrvl = payload.find(b"yrvl", gyvl + 4)
    if yrvl < 0:
        raise LiveryAnalysisError("C_livery 내부에서 yrvl 종료 블록을 찾지 못했습니다.")

    count_start = yrvl + 4
    count_bytes = len(LIVERY_SECTION_NAMES) * 4
    if count_start + count_bytes > len(payload):
        raise LiveryAnalysisError("리버리 영역별 배치 수 테이블이 잘렸습니다.")

    counts = struct.unpack_from(
        "<" + "I" * len(LIVERY_SECTION_NAMES), payload, count_start
    )
    section_counts = {
        name: int(count)
        for name, count in zip(LIVERY_SECTION_NAMES, counts)
    }
    total = sum(section_counts.values())

    # Corrupt data can otherwise produce plausible-looking but enormous uint32
    # values.  This guard is intentionally far above observed real liveries and
    # serves only as a fail-closed structural sanity check.
    if total > 10_000_000:
        raise LiveryAnalysisError(
            f"영역별 배치 수가 비정상적으로 큽니다. (total={total})"
        )

    return LiveryAnalysis(
        section_counts=section_counts,
        total_placements=total,
        populated_sections=sum(1 for count in counts if count > 0),
        payload_size=len(payload),
        gyvl_offset=gyvl,
        yrvl_offset=yrvl,
    )


def analyze_livery_file(path: Path | str) -> LiveryAnalysis:
    source = Path(path)
    if not source.is_file():
        raise LiveryAnalysisError("C_livery 파일을 찾을 수 없습니다.")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise LiveryAnalysisError(f"C_livery 파일을 읽지 못했습니다: {exc}") from exc
    return analyze_livery_bytes(raw)
