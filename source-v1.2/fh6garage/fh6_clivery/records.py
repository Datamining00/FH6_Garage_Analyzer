from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    offset: int
    length: int

    @property
    def end(self) -> int:
        return self.offset + self.length

    def to_dict(self) -> dict[str, int]:
        return {"offset": self.offset, "length": self.length, "end": self.end}


@dataclass(frozen=True)
class RawRecord:
    kind: str
    span: SourceSpan
    raw: bytes
    evidence_state: str
    marker_hex: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "span": self.span.to_dict(),
            "raw_hex": self.raw.hex(),
            "marker_hex": self.marker_hex,
            "evidence_state": self.evidence_state,
        }


@dataclass(frozen=True)
class Transform:
    x: float = 0.0
    y: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    rotation: float = 0.0
    skew: float = 0.0
    source_span: SourceSpan | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "sx": self.sx,
            "sy": self.sy,
            "rotation": self.rotation,
            "skew": self.skew,
            "source_span": self.source_span.to_dict() if self.source_span else None,
        }
