from __future__ import annotations

import hashlib
import sqlite3
import struct
import tempfile
from pathlib import Path
import unittest
import zipfile

from fh6garage.preview3d.modelbin_morph import (
    BUNDLE_TAG,
    DXGI_R16G16B16A16_FLOAT,
    ID_METADATA_TAG,
    MESH_TAG,
    MORPH_BUFFER_TAG,
)
from fh6garage.preview3d.tire_asset import (
    TireAssetError,
    compare_tire_library_to_database,
    inspect_tire_archive,
    profile_tire_morph_archive,
    resolve_tire_archive,
    scan_tire_library,
)


def _half4(x: float, y: float, z: float, target: float) -> bytes:
    return struct.pack("<eeee", x, y, z, target)


def _tire_modelbin() -> bytes:
    position = b"".join(
        [
            _half4(0, 1, 0, 0),
            _half4(0, 0, 2, 1),
            _half4(3, 0, 0, 2),
            _half4(4, 0, 0, 3),
            _half4(-5, 0, 0, 4),
        ]
    )
    normal = b"".join(_half4(0, 0, 0, selector) for selector in range(5))
    raw = position + normal
    mbuf_payload = struct.pack(
        "<iiHBBi", 1, len(raw), len(raw), 4, 0, DXGI_R16G16B16A16_FLOAT
    ) + raw

    mesh = bytearray()
    mesh += struct.pack("<h", 0)
    mesh += struct.pack("<h", 1)
    mesh += struct.pack("<H", 3)
    mesh += bytes((0, 255))
    mesh += struct.pack("<H", 1)
    mesh += bytes((0,))
    mesh += bytes((0,))
    mesh += bytes((5,))
    mesh += bytes((0,))
    mesh += bytes((1,))
    mesh += struct.pack("<H", 4)
    mesh += struct.pack("<iiiiii", 0, 0, 0, 0, 3, 1)
    mesh += struct.pack("<i", 0)
    mesh += struct.pack("<i", 0)
    mesh += struct.pack("<i", 77)
    mesh += struct.pack("<i", -1)
    mesh_payload = bytes(mesh)

    header_size = 0x14
    blob_table_size = 2 * 0x18
    metadata_offset = header_size + blob_table_size
    id_data_offset = metadata_offset + 8
    mbuf_data_offset = id_data_offset + 4
    mesh_data_offset = mbuf_data_offset + len(mbuf_payload)
    data = bytearray(mesh_data_offset + len(mesh_payload))

    struct.pack_into("<I", data, 0, BUNDLE_TAG)
    data[4] = 1
    data[5] = 1
    struct.pack_into("<I", data, 0x10, 2)

    struct.pack_into("<I", data, 0x14, MORPH_BUFFER_TAG)
    data[0x18] = 1
    struct.pack_into("<H", data, 0x1A, 1)
    struct.pack_into(
        "<IIII", data, 0x1C, metadata_offset, mbuf_data_offset, 0, len(mbuf_payload)
    )

    mesh_header = 0x14 + 0x18
    struct.pack_into("<I", data, mesh_header, MESH_TAG)
    data[mesh_header + 4] = 1
    data[mesh_header + 5] = 4
    struct.pack_into("<H", data, mesh_header + 6, 0)
    struct.pack_into(
        "<IIII", data, mesh_header + 8, 0, mesh_data_offset, 0, len(mesh_payload)
    )

    struct.pack_into("<IHH", data, metadata_offset, ID_METADATA_TAG, 4 << 4, 8)
    struct.pack_into("<I", data, id_data_offset, 77)
    data[mbuf_data_offset : mbuf_data_offset + len(mbuf_payload)] = mbuf_payload
    data[mesh_data_offset : mesh_data_offset + len(mesh_payload)] = mesh_payload
    return bytes(data)


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
        modelbin = _tire_modelbin()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("tirel_slick.modelbin", modelbin)
            bundle.writestr("tireR_slick.modelbin", modelbin)
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

    def test_profiles_five_target_tire_morphs_read_only(self) -> None:
        temp, _root, archive = self._fixture()
        with temp:
            before = self._sha256(archive)
            report = profile_tire_morph_archive(archive)
            after = self._sha256(archive)

            self.assertEqual(before, after)
            self.assertTrue(report.archive_read_only_unchanged)
            self.assertEqual(len(report.modelbins), 2)
            self.assertTrue(report.left_right_morph_buffers_identical)
            for model in report.modelbins:
                self.assertEqual(model["weighted_mesh_count"], 1)
                self.assertEqual(model["damage_mesh_count"], 0)
                self.assertEqual(model["unresolved_weighted_mesh_blob_indices"], [])
                profiles = model["profiles"]
                self.assertEqual(len(profiles), 1)
                selector_stats = profiles[0]["profile"]["selectors"]
                self.assertEqual([item["selector"] for item in selector_stats], [0, 1, 2, 3, 4])
                self.assertEqual(selector_stats[3]["max_abs_delta"][0], 4.0)
                self.assertEqual(selector_stats[4]["max_abs_delta"][0], 5.0)

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
