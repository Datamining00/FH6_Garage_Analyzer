from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path
import unittest
import zipfile

from fh6garage.preview3d.tire_asset import (
    TireAssetError,
    compare_tire_library_to_database,
    inspect_tire_archive,
    resolve_tire_archive,
    scan_tire_library,
)


class TireAssetTests(unittest.TestCase):
    def _fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / "Forza Horizon 6"
        cars = root / "Content" / "media" / "cars"
        tires = cars / "_library" / "scene" / "tires"
        tires.mkdir(parents=True)

        with zipfile.ZipFile(cars / "FER_FXX_05.zip", "w") as bundle:
            bundle.writestr("carclips_1006.clipd", b"fixture")

        archive = tires / "tire_slick.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(
                "_library/scene/tires/tire_Slick/tireL_Slick.modelbin",
                b"left-modelbin",
            )
            bundle.writestr(
                "_library/scene/tires/tire_Slick/tireR_Slick.modelbin",
                b"right-modelbin",
            )
            bundle.writestr("textures/tire_slick_d.dds", b"texture")

        for name in ("tire_slick_FE.zip", "tire_semi_slick_Dually_FE.zip"):
            with zipfile.ZipFile(tires / name, "w") as bundle:
                bundle.writestr("placeholder.modelbin", b"fixture")
        return temp, root, archive

    def _database(self, root: Path) -> Path:
        database = root / "fh6_game_db.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "CREATE TABLE List_UpgradeTireCompound "
                "(Id INTEGER, Ordinal INTEGER, IsStock INTEGER, TireModelName TEXT)"
            )
            connection.executemany(
                "INSERT INTO List_UpgradeTireCompound VALUES (?, ?, ?, ?)",
                [
                    (1, 1006, 1, "Slick"),
                    (2, 1006, 0, "Slick_FE"),
                    (3, 1229, 1, "semi_slick_Dually_FE"),
                    (4, 1260, 1, "Wet"),
                    (5, 1260, 0, "Slick"),
                ],
            )
            connection.commit()
        finally:
            connection.close()
        return database

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_resolves_native_tire_archive_case_insensitively(self) -> None:
        temp, root, archive = self._fixture()
        with temp:
            resolved = resolve_tire_archive(root, "Slick")
            self.assertTrue(
                resolved.samefile(archive),
                f"resolved tire archive points to a different file: {resolved} != {archive}",
            )

    def test_exact_model_name_does_not_collapse_tire_variants(self) -> None:
        temp, root, archive = self._fixture()
        with temp:
            self.assertTrue(resolve_tire_archive(root, "Slick").samefile(archive))
            self.assertEqual(resolve_tire_archive(root, "Slick_FE").name, "tire_slick_FE.zip")
            self.assertEqual(
                resolve_tire_archive(root, "semi_slick_Dually_FE").name,
                "tire_semi_slick_Dually_FE.zip",
            )

    def test_catalog_preserves_full_native_tire_model_names(self) -> None:
        temp, root, _archive = self._fixture()
        with temp:
            catalog = scan_tire_library(root)
            self.assertEqual(
                [item.tire_model_name for item in catalog.entries],
                ["semi_slick_Dually_FE", "slick", "slick_FE"],
            )
            self.assertEqual(catalog.duplicate_model_names, ())

    def test_database_coverage_matches_exact_model_names_read_only(self) -> None:
        temp, root, _archive = self._fixture()
        with temp:
            database = self._database(root)
            before = self._sha256(database)
            report = compare_tire_library_to_database(root, database)
            after = self._sha256(database)

            self.assertEqual(before, after)
            self.assertTrue(report.database_read_only_unchanged)
            self.assertEqual(
                report.database_model_names,
                ("semi_slick_Dually_FE", "Slick", "Slick_FE", "Wet"),
            )
            self.assertEqual(report.missing_database_model_names, ("Wet",))
            self.assertEqual(report.missing_stock_model_names, ("Wet",))
            self.assertEqual(report.unused_library_model_names, ())
            self.assertEqual(report.as_dict()["database_coverage_ratio"], 0.75)
            self.assertEqual(report.as_dict()["stock_coverage_ratio"], 2 / 3)

    def test_reports_modelbin_candidates_without_modifying_archive(self) -> None:
        temp, root, archive = self._fixture()
        with temp:
            before = archive.read_bytes()
            report = inspect_tire_archive(root, "Slick")
            after = archive.read_bytes()

            self.assertEqual(before, after)
            self.assertEqual(report.archive_name, "tire_slick.zip")
            self.assertEqual(report.entry_count, 3)
            self.assertEqual(len(report.modelbin_entries), 2)
            self.assertEqual(len(report.preferred_modelbin_entries), 2)
            self.assertTrue(
                all(entry.casefold().endswith(".modelbin") for entry in report.modelbin_entries)
            )

    def test_missing_native_tire_archive_fails_closed(self) -> None:
        temp, root, _archive = self._fixture()
        with temp:
            with self.assertRaisesRegex(TireAssetError, "was not found"):
                resolve_tire_archive(root, "Wet")

    def test_path_like_tire_model_name_is_rejected(self) -> None:
        temp, root, _archive = self._fixture()
        with temp:
            for value in ("../Slick", "foo/bar", r"foo\\bar", "C:Slick"):
                with self.subTest(value=value):
                    with self.assertRaises(TireAssetError):
                        resolve_tire_archive(root, value)


if __name__ == "__main__":
    unittest.main()
