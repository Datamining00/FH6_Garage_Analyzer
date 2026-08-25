from __future__ import annotations

from .models import LiveryRecord


def is_auction_livery(record: object | None) -> bool:
    """Return whether a record is outside FH6's My Designs navigation scope."""
    return isinstance(record, LiveryRecord) and record.kind == "SoulBoundLivery"
