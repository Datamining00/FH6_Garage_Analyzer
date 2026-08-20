from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib


class CliveryDecodeError(ValueError):
    """Raised when Milestone 1 cannot safely identify a C_livery container."""


@dataclass(frozen=True)
class ContainerInfo:
    source_kind: str
    raw_length: int
    payload_offset: int
    compressed_length: int | None
    declared_uncompressed_length: int | None
    actual_uncompressed_length: int

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "source_kind": self.source_kind,
            "raw_length": self.raw_length,
            "payload_offset": self.payload_offset,
            "compressed_length": self.compressed_length,
            "declared_uncompressed_length": self.declared_uncompressed_length,
            "actual_uncompressed_length": self.actual_uncompressed_length,
        }


def inflate_clivery(raw: bytes | bytearray | memoryview) -> tuple[bytes, ContainerInfo]:
    """Return one decompressed FH6 C_livery payload and read-only container metadata."""
    data = bytes(raw)
    if data.startswith(b"vlrc"):
        return data, ContainerInfo(
            source_kind="inflated-payload",
            raw_length=len(data),
            payload_offset=0,
            compressed_length=None,
            declared_uncompressed_length=None,
            actual_uncompressed_length=len(data),
        )

    if len(data) < 8:
        raise CliveryDecodeError("C_livery is too short for the 8-byte Forza container header")

    compressed_length, declared_uncompressed_length = struct.unpack_from("<II", data, 0)
    if compressed_length <= 0:
        raise CliveryDecodeError("C_livery declares an empty compressed payload")

    expected_length = 8 + compressed_length
    if expected_length != len(data):
        raise CliveryDecodeError(
            "C_livery compressed length does not match file size "
            f"({compressed_length} compressed bytes, {len(data) - 8} available)"
        )

    compressed = data[8:expected_length]
    try:
        payload = zlib.decompress(compressed)
    except zlib.error as exc:
        raise CliveryDecodeError(f"C_livery zlib payload could not be decompressed: {exc}") from exc

    if len(payload) != declared_uncompressed_length:
        raise CliveryDecodeError(
            "C_livery decompressed length does not match header "
            f"({declared_uncompressed_length} declared, {len(payload)} actual)"
        )
    if not payload.startswith(b"vlrc"):
        raise CliveryDecodeError("decompressed payload does not begin with the expected 'vlrc' tag")

    return payload, ContainerInfo(
        source_kind="fh6-zlib-container",
        raw_length=len(data),
        payload_offset=8,
        compressed_length=compressed_length,
        declared_uncompressed_length=declared_uncompressed_length,
        actual_uncompressed_length=len(payload),
    )
