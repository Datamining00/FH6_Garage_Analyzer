from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import struct

from .container import CliveryDecodeError, ContainerInfo, inflate_clivery
from .diagnostics import Diagnostic


FORMAT_ID = "fh6-assistant-clivery-scene-v1"
SECTION_NAMES = (
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
GYVL_HEADER_SIZE = 0x15
SECTION_COUNTER_COUNT = 11
SECTION_COUNTER_BYTES = SECTION_COUNTER_COUNT * 4
SECTION_COUNTER_TRAILING_BYTES = 4


@dataclass(frozen=True)
class SectionCount:
    slot: int
    name: str
    declared_count: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "slot": self.slot,
            "name": self.name,
            "declared_count": self.declared_count,
        }


@dataclass(frozen=True)
class CliveryMilestone1:
    car_id: int
    container: ContainerInfo
    gyvl_offset: int
    body_start: int
    body_end: int
    sections: tuple[SectionCount, ...]
    diagnostics: tuple[Diagnostic, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "format": FORMAT_ID,
            "car_id": self.car_id,
            "container": self.container.to_dict(),
            "gyvl_offset": self.gyvl_offset,
            "body_start": self.body_start,
            "body_end": self.body_end,
            "sections": [section.to_dict() for section in self.sections],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise CliveryDecodeError(f"u32 field at 0x{offset:x} is truncated")
    return struct.unpack_from("<I", data, offset)[0]


def _find_gyvl(payload: bytes) -> tuple[int, int, int]:
    search_from = 0x1A
    candidates: list[tuple[int, int]] = []
    pos = payload.find(b"gyvl", search_from)
    while pos >= 0:
        body_start = pos + GYVL_HEADER_SIZE
        if pos >= 4 and body_start <= len(payload):
            body_end = payload.find(b"yrvl", body_start)
            minimum_counter_end = (
                body_end
                + 4
                + SECTION_COUNTER_BYTES
                + SECTION_COUNTER_TRAILING_BYTES
            )
            successor_tag = payload.find(b"yrvl", minimum_counter_end)
            declared_gyvl_length = _read_u32(payload, pos - 4)
            actual_gyvl_length = body_end - pos
            if (
                body_end >= body_start
                and minimum_counter_end <= len(payload)
                and successor_tag >= minimum_counter_end
                and declared_gyvl_length == actual_gyvl_length
            ):
                candidates.append((pos, body_end))
        pos = payload.find(b"gyvl", pos + 1)

    if not candidates:
        raise CliveryDecodeError(
            "no structurally bounded 'gyvl' artwork chunk with a matching declared length and readable section-counter record was found"
        )

    gyvl_offset, body_end = candidates[0]
    return gyvl_offset, gyvl_offset + GYVL_HEADER_SIZE, body_end


def decode_clivery_bytes(raw: bytes | bytearray | memoryview) -> CliveryMilestone1:
    payload, container = inflate_clivery(raw)
    if len(payload) < 0x1A or payload[:4] != b"vlrc":
        raise CliveryDecodeError("C_livery payload is missing the minimum 'vlrc' root metadata")

    diagnostics: list[Diagnostic] = []
    car_id = _read_u32(payload, 0x10)
    gyvl_offset, body_start, body_end = _find_gyvl(payload)

    counter_start = body_end + 4
    counter_end = counter_start + SECTION_COUNTER_BYTES
    counts = tuple(_read_u32(payload, counter_start + slot * 4) for slot in range(SECTION_COUNTER_COUNT))
    trailing_counter = _read_u32(payload, counter_end)
    declared_gyvl_length = _read_u32(payload, gyvl_offset - 4)

    sections = tuple(
        SectionCount(slot=slot, name=name, declared_count=counts[slot])
        for slot, name in enumerate(SECTION_NAMES)
    )

    diagnostics.append(
        Diagnostic(
            severity="info",
            code="BODY_END_GYVL_LENGTH_CONFIRMED",
            message=(
                "body_end is the post-artwork 'yrvl' boundary and matches the declared gyvl "
                f"length field ({declared_gyvl_length} bytes) immediately preceding the gyvl tag"
            ),
            offset=body_end,
            evidence_state="CONFIRMED",
        )
    )
    diagnostics.append(
        Diagnostic(
            severity="info",
            code="SECTION_COUNTER_LAYOUT_CONFIRMED",
            message=(
                "eleven little-endian u32 section counters are read immediately after the "
                "post-artwork 'yrvl' tag; the layout matches repeated raw FH6 sample observations"
            ),
            offset=counter_start,
            evidence_state="CONFIRMED",
        )
    )
    diagnostics.append(
        Diagnostic(
            severity="info",
            code="SECTION_COUNTER_TRAILING_VALUE",
            message=(
                "one additional little-endian u32 follows the eleven section counters; "
                f"its position is confirmed but its higher-level semantic role is not interpreted in Milestone 1 (value={trailing_counter})"
            ),
            offset=counter_end,
            evidence_state="CONFIRMED",
        )
    )

    return CliveryMilestone1(
        car_id=car_id,
        container=container,
        gyvl_offset=gyvl_offset,
        body_start=body_start,
        body_end=body_end,
        sections=sections,
        diagnostics=tuple(diagnostics),
    )


def decode_clivery_file(path: str | Path) -> CliveryMilestone1:
    source = Path(path)
    return decode_clivery_bytes(source.read_bytes())


def decode_clivery_file_to_json(path: str | Path, *, indent: int = 2) -> str:
    return decode_clivery_file(path).to_json(indent=indent)
