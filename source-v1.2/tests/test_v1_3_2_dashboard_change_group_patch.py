from __future__ import annotations

from types import SimpleNamespace

from fh6garage.refresh_history import (
    LiveryRefreshChange,
    LiveryRefreshDiff,
    LiverySnapshotEntry,
)
from fh6garage.v1_3_2_dashboard_change_group_patch import (
    _categorized_changes,
    _update_dashboard_summary,
)


class _TextSink:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value: str) -> None:
        self.text = str(value)


class _Card:
    def __init__(self) -> None:
        self.title = _TextSink()
        self.value = _TextSink()


def _entry(name: str, *, digest: str, kind: str = "Livery") -> LiverySnapshotEntry:
    return LiverySnapshotEntry(
        identity=f"{kind}:{name.casefold()}",
        kind=kind,
        container_name=name,
        guid="",
        car_id=1,
        name=name,
        creator="creator",
        description="",
        created="",
        decal_count=None,
        platform_code=None,
        content_sha256=digest,
        thumbnail_cache="",
    )


def test_recent_changes_are_grouped_as_add_remove_duplicate_without_losing_changed_pairs() -> None:
    duplicate_added = _entry("Livery_1_dup", digest="same")
    unique_added = _entry("Livery_1_unique", digest="unique")
    removed = _entry("Livery_1_removed", digest="removed")
    changed_before = _entry("Livery_1_before", digest="before")
    changed_after = _entry("Livery_1_after", digest="after")

    current_records = [
        SimpleNamespace(kind="Livery", content_sha256="same"),
        SimpleNamespace(kind="Livery", content_sha256="same"),
        SimpleNamespace(kind="Livery", content_sha256="unique"),
        SimpleNamespace(kind="Livery", content_sha256="after"),
    ]
    window = SimpleNamespace(result=SimpleNamespace(liveries=current_records))
    diff = LiveryRefreshDiff(
        False,
        "scope",
        added=[
            LiveryRefreshChange("added", after=duplicate_added),
            LiveryRefreshChange("added", after=unique_added),
        ],
        removed=[LiveryRefreshChange("removed", before=removed)],
        changed=[LiveryRefreshChange("changed", before=changed_before, after=changed_after)],
    )

    groups = _categorized_changes(window, diff)

    assert [entry.container_name for entry in groups["duplicate"]] == ["Livery_1_dup"]
    assert [entry.container_name for entry in groups["added"]] == [
        "Livery_1_unique",
        "Livery_1_after",
    ]
    assert [entry.container_name for entry in groups["removed"]] == [
        "Livery_1_removed",
        "Livery_1_before",
    ]


def test_dashboard_summary_shows_applied_over_total_and_unknown_when_memory_is_unavailable() -> None:
    regular_applied = SimpleNamespace(kind="Livery", state="applied")
    regular_unapplied = SimpleNamespace(kind="Livery", state="unapplied")
    auction_applied = SimpleNamespace(kind="SoulBoundLivery", state="applied")
    auction_unknown = SimpleNamespace(kind="SoulBoundLivery", state="unknown")

    window = SimpleNamespace(
        card_livery=_Card(),
        card_auction=_Card(),
        result=SimpleNamespace(
            liveries=[
                regular_applied,
                regular_unapplied,
                auction_applied,
                auction_unknown,
            ]
        ),
        _fh6_memory_state_usable=lambda: True,
        _fh6_memory_livery_state_for_record=lambda record: record.state,
    )

    _update_dashboard_summary(window)
    assert window.card_livery.value.text == "1 / 2"
    assert window.card_auction.value.text == "1 / 2"

    window._fh6_memory_state_usable = lambda: False
    _update_dashboard_summary(window)
    assert window.card_livery.value.text == "— / 2"
    assert window.card_auction.value.text == "— / 2"
