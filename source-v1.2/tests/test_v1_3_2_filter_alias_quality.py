from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from fh6garage.creator_aliases import CreatorAliasGroup, CreatorAliasStore
from fh6garage.v1_3_2_filter_alias_quality_patch import (
    _actual_creator_names,
    _dissolve_alias_group,
    _observed_creator_names,
)


class _Header:
    def __init__(self, creator: str):
        self.creator = creator


class _Record:
    def __init__(self, creator: str):
        self.header = _Header(creator)


class FilterAliasQualityTests(unittest.TestCase):
    def test_dissolve_group_writes_once_and_removes_group(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = CreatorAliasStore(Path(td) / "creator_aliases.json")
            store.groups = [CreatorAliasGroup("Current", ["OldA", "OldB", "OldC"])]

            writes = 0

            def fake_write() -> bool:
                nonlocal writes
                writes += 1
                return True

            store._write = fake_write  # type: ignore[method-assign]

            self.assertTrue(_dissolve_alias_group(store, "OldB"))
            self.assertEqual(writes, 1)
            self.assertEqual(store.groups, [])
            self.assertFalse(_dissolve_alias_group(store, "OldC"))
            self.assertEqual(writes, 1)

    def test_observed_names_excludes_stale_singletons(self) -> None:
        window = SimpleNamespace(
            result=SimpleNamespace(
                liveries=[_Record("LiveLivery")],
                tunings=[_Record("LiveTune")],
            ),
            creator_aliases=SimpleNamespace(
                groups=[
                    CreatorAliasGroup("LinkedNow", ["LinkedOld"]),
                    CreatorAliasGroup("StaleSingleton", []),
                ]
            ),
        )

        self.assertEqual(
            _actual_creator_names(window),
            ["LiveLivery", "LiveTune"],
        )
        names = _observed_creator_names(window)
        self.assertIn("LiveLivery", names)
        self.assertIn("LiveTune", names)
        self.assertIn("LinkedNow", names)
        self.assertIn("LinkedOld", names)
        self.assertNotIn("StaleSingleton", names)

    def test_actual_names_are_case_insensitive_deduplicated(self) -> None:
        window = SimpleNamespace(
            result=SimpleNamespace(
                liveries=[_Record("Creator"), _Record("creator")],
                tunings=[_Record("CREATOR")],
            )
        )
        self.assertEqual(_actual_creator_names(window), ["Creator"])


if __name__ == "__main__":
    unittest.main()
