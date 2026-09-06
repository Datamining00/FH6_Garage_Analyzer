from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from fh6garage.preview3d.modelbin_morph import (
    BUNDLE_TAG,
    MeshMorphBinding,
    ModelbinMorphError,
    ModelbinMorphInventory,
    MorphBindingResolution,
    MorphBufferInfo,
)
from fh6garage.preview3d.modelbin_morph_index_profile import MeshIndexAddressingProfile
from fh6garage.preview3d.vehicle_morph_diagnostic import (
    VehicleMorphDiagnosticError,
    classify_modelbin_path,
    inspect_vehicle_morph_archive,
    write_vehicle_morph_report,
)


def _half4(x: float, y: float, z: float, selector: float) -> bytes:
    return struct.pack("<eeee", x, y, z, selector)


def _empty_modelbin() -> bytes:
    data = bytearray(0x14)
    struct.pack_into("<I", data, 0, BUNDLE_TAG)
    data[4] = 1
    data[5] = 1
    struct.pack_into("<I", data, 0x10, 0)
    return bytes(data)


def _inventory(*, damage: bool = False) -> ModelbinMorphInventory:
    raw = (
        _half4(1, 0, 0, 0)
        + _half4(0, 2, 0, 1)
        + _half4(0, 0, 1, 0)
        + _half4(0, 1, 0, 1)
    )
    buffer = MorphBufferInfo(
        blob_index=0,
        identifier_id=77,
        version_major=1,
        version_minor=0,
        length=1,
        size=len(raw),
        stride=len(raw),
        sub_element_count=4,
        format=10,
        raw_data=raw,
    )
    mesh = MeshMorphBinding(
        blob_index=1,
        version_major=1,
        version_minor=13,
        morph_target_count=2,
        is_morph_damage=damage,
        indexed_vertex_offset=0,
        morph_data_buffer_index=77,
    )
    resolution = MorphBindingResolution(
        mesh_blob_index=1,
        morph_data_buffer_index=77,
        morph_buffer_blob_index=0,
        resolved_by="identifier",
    )
    return ModelbinMorphInventory(1, 1, (buffer,), (mesh,), (resolution,))


def _index_profile() -> MeshIndexAddressingProfile:
    return MeshIndexAddressingProfile(
        mesh_blob_index=1,
        mesh_version="1.13",
        index_buffer_blob_index=2,
        index_buffer_blob_count=1,
        index_buffer_resolution="fts_first_indb",
        index_buffer_index=0,
        index_buffer_offset_bytes=0,
        index_buffer_draw_offset=7422,
        indexed_vertex_offset=-3212,
        index_count=3444,
        primitive_count=1148,
        is_32bit_indices=True,
        index_stride=4,
        serialized_index_buffer_stride=4,
        stride_matches_mesh=True,
        index_byte_start=29688,
        index_byte_end=43464,
        min_vertex_index=3212,
        max_vertex_index=4136,
        resolved_vertex_start=0,
        resolved_vertex_end=924,
        resolved_vertex_count=925,
    )


def _write_vehicle_archive(path: Path) -> None:
    modelbin_entry = "Scene/Wheels/FER_FXX_05_wheel.modelbin"
    resolved_ref = "game:\\media\\cars\\FER_FXX_05\\Scene\\Wheels\\FER_FXX_05_wheel.modelbin"
    unresolved_ref = "game:\\media\\cars\\FER_FXX_05\\Scene\\Brakes\\missing_brake.modelbin"
    carbin = (resolved_ref + "\x00" + unresolved_ref + "\x00").encode("ascii")
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("FER_FXX_05.carbin", carbin)
        bundle.writestr(modelbin_entry, _empty_modelbin())
        bundle.writestr("carclips_1006.clipd", b"")


class VehicleMorphDiagnosticTests(unittest.TestCase):
    def test_path_classification_is_diagnostic_only_and_stable(self):
        self.assertEqual(classify_modelbin_path("Scene/Wheels/rim.modelbin"), "wheel")
        self.assertEqual(classify_modelbin_path("Scene/Tires/tire.modelbin"), "tire")
        self.assertEqual(classify_modelbin_path("Scene/Brakes/rotor.modelbin"), "brake")
        self.assertEqual(classify_modelbin_path("Scene/Body/body.modelbin"), "other")

    def test_archive_diagnostic_reuses_carbin_resolution_and_is_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "FER_FXX_05.zip"
            _write_vehicle_archive(archive)
            before = archive.read_bytes()
            with patch(
                "fh6garage.preview3d.vehicle_morph_diagnostic.parse_modelbin_morph_inventory",
                return_value=_inventory(damage=False),
            ), patch(
                "fh6garage.preview3d.vehicle_morph_diagnostic.profile_modelbin_index_addressing",
                return_value=(_index_profile(),),
            ):
                report = inspect_vehicle_morph_archive(
                    archive,
                    "FER_FXX_05.carbin",
                    "FER_FXX_05",
                )
            self.assertEqual(archive.read_bytes(), before)
            self.assertFalse(report.game_data_modified)
            self.assertEqual(report.discovered_modelbin_references, 2)
            self.assertEqual(report.resolved_modelbin_references, 1)
            self.assertEqual(len(report.unresolved_modelbin_references), 1)
            self.assertEqual(report.referenced_modelbins, 1)
            self.assertEqual(report.parsed_modelbins, 1)
            self.assertEqual(report.modelbins_with_morph, 1)
            self.assertEqual(report.morph_buffers, 1)
            self.assertEqual(report.morph_meshes, 1)
            self.assertEqual(report.weighted_morph_meshes, 1)
            self.assertEqual(report.damage_morph_meshes, 0)
            self.assertEqual(report.category_counts, {"wheel": 1})
            self.assertEqual(report.modelbins[0].category, "wheel")
            self.assertIsNone(report.modelbins[0].parse_error)

            profiles = report.modelbins[0].weighted_target_profiles
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0]["mesh_blob_indices"], (1,))
            self.assertEqual(profiles[0]["morph_target_count"], 2)
            self.assertEqual(profiles[0]["morph_buffer_blob_index"], 0)
            self.assertEqual(profiles[0]["resolved_by"], "identifier")
            self.assertIsNone(profiles[0]["profile_error"])
            profile = profiles[0]["profile"]
            self.assertIsNotNone(profile)
            self.assertEqual(profile["missing_selectors"], ())
            self.assertEqual([item["selector"] for item in profile["selectors"]], [0, 1])
            self.assertEqual(profile["selectors"][0]["sum_abs_delta"], (1.0, 0.0, 0.0))
            self.assertEqual(profile["selectors"][1]["sum_abs_delta"], (0.0, 2.0, 0.0))

            index_profiles = report.modelbins[0].index_addressing_profiles
            self.assertEqual(len(index_profiles), 1)
            self.assertIsNone(report.modelbins[0].index_addressing_error)
            self.assertEqual(index_profiles[0]["mesh_blob_index"], 1)
            self.assertEqual(index_profiles[0]["indexed_vertex_offset"], -3212)
            self.assertEqual(index_profiles[0]["min_vertex_index"], 3212)
            self.assertEqual(index_profiles[0]["resolved_vertex_start"], 0)
            self.assertEqual(index_profiles[0]["resolved_vertex_end"], 924)

    def test_damage_binding_is_not_profiled_as_weighted_geometry(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "FER_FXX_05.zip"
            _write_vehicle_archive(archive)
            with patch(
                "fh6garage.preview3d.vehicle_morph_diagnostic.parse_modelbin_morph_inventory",
                return_value=_inventory(damage=True),
            ), patch(
                "fh6garage.preview3d.vehicle_morph_diagnostic.profile_modelbin_index_addressing",
                side_effect=AssertionError("damage morph must not request weighted index profile"),
            ):
                report = inspect_vehicle_morph_archive(
                    archive,
                    "FER_FXX_05.carbin",
                    "FER_FXX_05",
                )
            self.assertEqual(report.damage_morph_meshes, 1)
            self.assertEqual(report.weighted_morph_meshes, 0)
            self.assertEqual(report.modelbins[0].weighted_target_profiles, ())
            self.assertEqual(report.modelbins[0].index_addressing_profiles, ())
            self.assertIsNone(report.modelbins[0].index_addressing_error)

    def test_index_addressing_failure_does_not_invalidate_morph_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "FER_FXX_05.zip"
            _write_vehicle_archive(archive)
            with patch(
                "fh6garage.preview3d.vehicle_morph_diagnostic.parse_modelbin_morph_inventory",
                return_value=_inventory(damage=False),
            ), patch(
                "fh6garage.preview3d.vehicle_morph_diagnostic.profile_modelbin_index_addressing",
                side_effect=ModelbinMorphError("IndB fixture unavailable"),
            ):
                report = inspect_vehicle_morph_archive(
                    archive,
                    "FER_FXX_05.carbin",
                    "FER_FXX_05",
                )
            self.assertEqual(report.parsed_modelbins, 1)
            self.assertEqual(report.weighted_morph_meshes, 1)
            self.assertEqual(report.modelbins[0].index_addressing_profiles, ())
            self.assertEqual(report.modelbins[0].index_addressing_error, "IndB fixture unavailable")
            self.assertIsNone(report.modelbins[0].parse_error)

    def test_parse_failure_is_recorded_without_mutating_archive(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "FER_FXX_05.zip"
            _write_vehicle_archive(archive)
            before = archive.read_bytes()
            with patch(
                "fh6garage.preview3d.vehicle_morph_diagnostic.parse_modelbin_morph_inventory",
                side_effect=ModelbinMorphError("unsupported fixture"),
            ):
                report = inspect_vehicle_morph_archive(
                    archive,
                    "FER_FXX_05.carbin",
                    "FER_FXX_05",
                )
            self.assertEqual(archive.read_bytes(), before)
            self.assertEqual(report.referenced_modelbins, 1)
            self.assertEqual(report.parsed_modelbins, 0)
            self.assertEqual(report.morph_meshes, 0)
            self.assertEqual(report.modelbins[0].parse_error, "unsupported fixture")
            self.assertEqual(report.modelbins[0].weighted_target_profiles, ())
            self.assertEqual(report.modelbins[0].index_addressing_profiles, ())
            self.assertIsNone(report.modelbins[0].index_addressing_error)

    def test_report_writer_refuses_source_archive_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cars = root / "cars"
            cars.mkdir()
            archive = cars / "FER_FXX_05.zip"
            _write_vehicle_archive(archive)
            report = inspect_vehicle_morph_archive(
                archive,
                "FER_FXX_05.carbin",
                "FER_FXX_05",
            )
            with self.assertRaises(VehicleMorphDiagnosticError):
                write_vehicle_morph_report(report, cars / "morph.json")

            safe_output = root / "diagnostics" / "morph.json"
            written = write_vehicle_morph_report(report, safe_output)
            self.assertEqual(written, safe_output.resolve())
            self.assertTrue(safe_output.is_file())


if __name__ == "__main__":
    unittest.main()
