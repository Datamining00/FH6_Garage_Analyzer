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
from fh6garage.preview3d.vehicle_morph_diagnostic import (
    VehicleMorphDiagnosticError,
    classify_modelbin_path,
    inspect_vehicle_morph_archive,
    write_vehicle_morph_report,
)


def _empty_modelbin() -> bytes:
    data = bytearray(0x14)
    struct.pack_into("<I", data, 0, BUNDLE_TAG)
    data[4] = 1
    data[5] = 1
    struct.pack_into("<I", data, 0x10, 0)
    return bytes(data)


def _inventory(*, damage: bool = False) -> ModelbinMorphInventory:
    buffer = MorphBufferInfo(
        blob_index=0,
        identifier_id=77,
        version_major=1,
        version_minor=0,
        length=1,
        size=8,
        stride=8,
        sub_element_count=4,
        format=10,
        raw_data=b"\x00" * 8,
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
