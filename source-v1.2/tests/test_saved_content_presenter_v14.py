from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.saved_content_presenter import (
    FilterState,
    build_grid_sections,
    build_search_text,
    filter_matches,
    search_matches,
)


class SavedContentPresenterTests(unittest.TestCase):
    def test_filter_modes_are_combined_with_and_semantics(self) -> None:
        state = FilterState(checked=True, note="memo", triangle=False)
        self.assertTrue(filter_matches("livery", {1, 3, 6}, state))
        self.assertFalse(filter_matches("livery", {1, 4}, state))

    def test_duplicate_mode_only_restricts_liveries(self) -> None:
        state = FilterState(duplicate=False)
        self.assertFalse(filter_matches("livery", {9}, state))
        self.assertTrue(filter_matches("tuning", {9}, state))

    def test_unmarked_mode_excludes_every_annotation_marker(self) -> None:
        self.assertTrue(filter_matches("livery", {10}, FilterState()))
        self.assertFalse(
            filter_matches("livery", {10}, FilterState(excluded=True))
        )

    def test_search_text_includes_vehicle_creator_description_and_note(self) -> None:
        item = LiveryRecord(
            container_name="one",
            container_path=Path("one"),
            kind="custom",
            header=HeaderInfo(
                name="Design",
                creator="Painter",
                car_id=7,
                description="Description",
            ),
        )
        text = build_search_text(item, lambda car_id: "2020 Example Car", "Memo")
        for value in ("design", "painter", "2020 example car", "description", "memo"):
            self.assertIn(value, text)
        self.assertTrue(search_matches(text, " EXAMPLE "))
        self.assertFalse(search_matches(text, "missing"))

    def test_grid_sections_preserve_group_and_item_order(self) -> None:
        items = [
            {"vehicle": "b", "creator": "x", "value": 1},
            {"vehicle": "a", "creator": "y", "value": 2},
            {"vehicle": "b", "creator": "z", "value": 3},
        ]
        sections = build_grid_sections(
            items,
            group_mode="vehicle",
            vehicle_key=lambda item: item["vehicle"],
            vehicle_label=lambda item: item["vehicle"].upper(),
            creator_key=lambda item: item["creator"],
            creator_label=lambda item: item["creator"].upper(),
        )
        self.assertEqual([section.key for section in sections], ["b", "a"])
        self.assertEqual(
            [item["value"] for item in sections[0].items],
            [1, 3],
        )

    def test_flat_grid_is_one_section_and_invalid_mode_is_rejected(self) -> None:
        arguments = dict(
            vehicle_key=str,
            vehicle_label=str,
            creator_key=str,
            creator_label=str,
        )
        sections = build_grid_sections(["a", "b"], group_mode="none", **arguments)
        self.assertEqual(sections[0].items, ("a", "b"))
        with self.assertRaises(ValueError):
            build_grid_sections([], group_mode="invalid", **arguments)


if __name__ == "__main__":
    unittest.main()
