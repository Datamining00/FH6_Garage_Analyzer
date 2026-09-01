from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.backup_export import load_index
from fh6garage.models import HeaderInfo
from fh6garage import v1_4_backup_repository_patch as patch_module
from fh6garage import v1_3_4_backup_import_refinement_patch as import_refinement


class V14BackupRepositoryTests(unittest.TestCase):
    def _container(self, root: Path, name: str) -> Path:
        container = root / name
        container.mkdir(parents=True)
        (container / "header").write_bytes(b"header")
        (container / "C_livery").write_bytes((name + " payload").encode("utf-8"))
        (container / "extra.bin").write_bytes(b"preserve me")
        return container

    def test_discovery_accepts_livery_and_soulbound_and_skips_tuning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._container(root, "Livery_101_20260830010101")
            self._container(root, "SoulBoundLivery_202_20260830020202")
            self._container(root, "Tuning_303_20260830030303")
            token = patch_module._ExternalImportToken()
            headers = {
                "Livery": HeaderInfo(name="Mine", creator="A", car_id=1),
                "SoulBoundLivery": HeaderInfo(name="Auction", creator="B", car_id=2),
            }
            with patch.object(
                patch_module,
                "read_header_file",
                side_effect=lambda _path, kind: headers[kind],
            ):
                records, unsupported, malformed = patch_module._discover_external_records(root, token)
            self.assertEqual({record.kind for record in records}, {"Livery", "SoulBoundLivery"})
            self.assertEqual(unsupported, 1)
            self.assertEqual(malformed, 0)

    def test_external_record_is_compatible_with_verified_repository_export(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            repo = base / "repo"
            source.mkdir()
            container = self._container(source, "Livery_777_20260830040404")
            with patch.object(
                patch_module,
                "read_header_file",
                return_value=HeaderInfo(name="External", creator="Painter", car_id=777),
            ):
                record = patch_module._external_record(container)
            summary = import_refinement._safe_export_records(repo, [record])
            self.assertEqual(len(summary.exported), 1)
            self.assertEqual(summary.failed, [])
            payload = load_index(repo)
            self.assertEqual(len(payload["entries"]), 1)
            copied = repo / payload["entries"][0]["relative_path"]
            self.assertEqual((copied / "extra.bin").read_bytes(), b"preserve me")
            self.assertEqual(payload["entries"][0]["kind"], "Livery")

    def test_source_contract_uses_shared_local_appdata_and_real_external_worker(self):
        text = Path("fh6garage/v1_4_backup_repository_patch.py").read_text(encoding="utf-8")
        self.assertIn("app_data_dir() / \"backup\"", text)
        self.assertNotIn("AppLocalDataLocation", text)
        self.assertIn("외부에서 가져오기", text)
        self.assertIn("_safe_export_records", text)
        self.assertIn("QMetaObject.invokeMethod", text)
        self.assertIn("_ExternalImportToken", text)
        self.assertIn("row.indexOf(refresh)", text)

    def test_v14_identity_and_build_outputs_are_named_v14(self):
        identity = Path("fh6garage/v1_4_identity_patch.py").read_text(encoding="utf-8")
        workflow = Path("../.github/workflows/build-v1.3.3-beta.yml").read_text(encoding="utf-8")
        standard = Path("FH6_Assistant_v1.4.spec").read_text(encoding="utf-8")
        portable = Path("FH6_Assistant_v1.4_portable.spec").read_text(encoding="utf-8")
        version = Path("version_info.txt").read_text(encoding="utf-8")
        app = Path("app.py").read_text(encoding="utf-8")
        package = Path("fh6garage/__init__.py").read_text(encoding="utf-8")
        build = Path("build_exe.ps1").read_text(encoding="utf-8")
        readme = Path("README.txt").read_text(encoding="utf-8")
        self.assertIn('WINDOW_TITLE = "FH6 Assistant v1.4 RC1"', identity)
        self.assertIn("Validate and build FH6 Assistant v1.4", workflow)
        self.assertIn("FH6_Assistant_v1.4_Standard", workflow)
        self.assertIn("FH6_Assistant_v1.4_Portable", workflow)
        self.assertIn("FH6_Assistant_v1.4_Source", workflow)
        self.assertIn("name='FH6 Assistant v1.4'", standard)
        self.assertIn("name='FH6 Assistant v1.4 Portable'", portable)
        self.assertIn("ProductVersion', '1.4'", version)
        self.assertIn('app.setApplicationVersion("1.4")', app)
        self.assertIn('__version__ = "1.4"', package)
        self.assertIn("FH6_Assistant_v1.4.spec", build)
        self.assertNotIn("FH6_Assistant_v1.3.3.spec", build)
        self.assertTrue(readme.startswith("FH6 Assistant v1.4"))


if __name__ == "__main__":
    unittest.main()
