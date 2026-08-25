from __future__ import annotations

from typing import Protocol

from .models import LiveryRecord

HIDDEN_MODE = 11
AUCTION_APPLIED_MODE = 12
AUCTION_UNAPPLIED_MODE = 13
HIDDEN_PREFERENCE_PREFIX = "hidden_livery_v1_3_2:"


class BooleanPreferences(Protocol):
    def get_bool(self, key: str, default: bool = False) -> bool: ...

    def set_bool(self, key: str, value: bool) -> None: ...


def hidden_preference_key(content_key: str) -> str:
    return f"{HIDDEN_PREFERENCE_PREFIX}{content_key}"


def is_livery_hidden(preferences: BooleanPreferences, content_key: str) -> bool:
    return preferences.get_bool(hidden_preference_key(content_key), False)


def set_livery_hidden(
    preferences: BooleanPreferences,
    content_key: str,
    hidden: bool,
) -> None:
    preferences.set_bool(hidden_preference_key(content_key), bool(hidden))


def is_auction_livery_applied(record: object) -> bool:
    """Return whether a SoulBound record resolves to an existing cache image."""
    if not isinstance(record, LiveryRecord) or record.kind != "SoulBoundLivery":
        return False
    path = record.thumbnail_path
    try:
        return bool(path is not None and path.is_file())
    except OSError:
        return False
