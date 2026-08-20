from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    offset: int | None = None
    evidence_state: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        result: dict[str, str | int | None] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.offset is not None:
            result["offset"] = self.offset
        if self.evidence_state is not None:
            result["evidence_state"] = self.evidence_state
        return result
