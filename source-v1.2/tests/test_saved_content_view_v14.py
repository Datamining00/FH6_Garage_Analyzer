from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.saved_content_view import (
    SortSpec,
    creator_alias_token,
    group_items,
    sort_cache_key,
    sort_records,
)


def record(
    name: str,
    *,
    car_id: int,
    creator: str = "",
    downloaded_at: float | None = None,
) -> LiveryRecord:
    return LiveryRecord(
        container_name=name,
        container_path=Path(name),
        kind="custom",
        header=HeaderInfo(name=name, car_id=car_id, creator=creator),
        downloaded_at=downloaded_at,
    )


class SavedContentViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = {
            1: "2020 Zeta Model",
            2: "2019 Alpha Model",
            3: "Unknown vehicle",
        }
        self.car_label = lambda car_id: self.labels.get(car_id, f"Car ID {car_id}")

    def test_brand_sort_uses_manufacturer_first_label(self) -> None:
        records = [record("z", car_id=1), record("a", car_id=2), record("u", car_id=3)]
        ordered = sort_records(records, SortSpec("brand"), self.car_label)
        self.assertEqual([item.container_name for item in ordered], ["a", "z", "u"])

    def test_creator_descending_keeps_missing_creator_last(self) -> None:
        records = [
            record("none", car_id=1),
            record("alpha", car_id=1, creator="Alpha"),
            record("zeta", car_id=2, creator="Zeta"),
        ]
        ordered = sort_records(records, SortSpec("creator", True), self.car_label)
        self.assertEqual([item.container_name for item in ordered], ["zeta", "alpha", "none"])

    def test_download_sort_keeps_unknown_dates_at_end(self) -> None:
        records = [
            record("none", car_id=1),
            record("old", car_id=1, downloaded_at=1.0),
            record("new", car_id=1, downloaded_at=2.0),
        ]
        ordered = sort_records(records, SortSpec("download", True), self.car_label)
        self.assertEqual([item.container_name for item in ordered], ["new", "old", "none"])

    def test_groups_preserve_first_seen_order(self) -> None:
        items = [("b", "B", 1), ("a", "A", 2), ("b", "ignored", 3)]
        grouped = group_items(items, lambda item: item[0], lambda item: item[1])
        self.assertEqual([group[0] for group in grouped], ["b", "a"])
        self.assertEqual(grouped[0][1], "B")
        self.assertEqual([item[2] for item in grouped[0][2]], [1, 3])

    def test_cache_key_changes_with_alias_and_database_revision(self) -> None:
        records = [record("one", car_id=1)]
        aliases = SimpleNamespace(
            groups=[SimpleNamespace(current="Now", previous=("Before",))]
        )
        base = dict(
            content_type="livery",
            result=object(),
            records=records,
            spec=SortSpec("creator"),
            initial_scan=False,
            aliases=aliases,
        )
        first = sort_cache_key(car_db_revision=1, **base)
        second = sort_cache_key(car_db_revision=2, **base)
        self.assertNotEqual(first, second)
        self.assertEqual(creator_alias_token(aliases), (("Now", ("Before",)),))

    def test_invalid_sort_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SortSpec("invalid")


if __name__ == "__main__":
    unittest.main()
