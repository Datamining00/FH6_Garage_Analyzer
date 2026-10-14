from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MIN_PREVIOUS = 50
DEFAULT_MAX_RETAINED_RATIO = 0.60
DEFAULT_MIN_ABSOLUTE_DROP = 25


@dataclass(frozen=True, slots=True)
class SnapshotDropDiagnostic:
    previous_count: int
    current_count: int
    dropped_count: int
    retained_ratio: float

    @property
    def drop_ratio(self) -> float:
        return 1.0 - self.retained_ratio


def detect_suspicious_snapshot_drop(
    previous_count: int,
    current_count: int,
    *,
    min_previous: int = DEFAULT_MIN_PREVIOUS,
    max_retained_ratio: float = DEFAULT_MAX_RETAINED_RATIO,
    min_absolute_drop: int = DEFAULT_MIN_ABSOLUTE_DROP,
) -> SnapshotDropDiagnostic | None:
    """Return a diagnostic only for unusually large active-livery count drops.

    This is deliberately conservative. A normal one/few-livery apply/unapply
    change must never trigger the guard. The caller decides whether to warn,
    log, or reject a result; this helper never changes scan state itself.
    """
    previous = max(0, int(previous_count))
    current = max(0, int(current_count))
    minimum_previous = max(1, int(min_previous))
    minimum_drop = max(1, int(min_absolute_drop))
    retained_limit = min(1.0, max(0.0, float(max_retained_ratio)))

    if previous < minimum_previous or current >= previous:
        return None

    dropped = previous - current
    if dropped < minimum_drop:
        return None

    retained_ratio = current / previous
    if retained_ratio > retained_limit:
        return None

    return SnapshotDropDiagnostic(
        previous_count=previous,
        current_count=current,
        dropped_count=dropped,
        retained_ratio=retained_ratio,
    )
