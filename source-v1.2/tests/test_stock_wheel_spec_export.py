from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "export_stock_wheel_specs_real_db.py"


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE Data_Car (
                Id INTEGER PRIMARY KEY,
                MediaName TEXT,
                FrontTireWidthMM REAL,
                FrontTireAspect REAL,
                FrontWheelDiameterIN REAL,
                RearTireWidthMM REAL,
                RearTireAspect REAL,
                RearWheelDiameterIN REAL
            );
            INSERT INTO Data_Car VALUES
              (1006, 'FER_FXX_05', 245, 35, 19, 345, 35, 19),
              (2000, 'TEST_INCOMPLETE', 0, 35, 18, 275, 35, 18);
            """
        )


class StockWheelSpecExportTests(unittest.TestCase):
    def test_exports_complete_rows_read_only_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "fh6_game_db.sqlite"
            output = root / "stock.json"
            report = root / "report.json"
            _fixture(database)
            before = _sha256(database)
            blob = _git_blob_sha1(database)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--db", str(database),
                    "--output", str(output),
                    "--report", str(report),
                    "--source-repository", "fixture/repo",
                    "--source-commit", "fixture-commit",
                    "--source-blob-sha1", blob,
                    "--min-complete", "1",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(_sha256(database), before)

            dataset = json.loads(output.read_text(encoding="utf-8"))
            diagnostics = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(dataset["format"], "fh6_stock_wheel_specs_v1")
            self.assertEqual(len(dataset["records"]), 1)
            self.assertEqual(dataset["records"][0]["car_id"], 1006)
            self.assertEqual(dataset["records"][0]["media_name"], "FER_FXX_05")
            self.assertEqual(dataset["records"][0]["front_tire_width_mm"], 245.0)
            self.assertEqual(dataset["records"][0]["rear_tire_width_mm"], 345.0)
            self.assertEqual(dataset["records"][0]["front_wheel_diameter_in"], 19.0)
            self.assertEqual(dataset["records"][0]["rear_wheel_diameter_in"], 19.0)
            self.assertEqual(diagnostics["source_row_count"], 2)
            self.assertEqual(diagnostics["complete_record_count"], 1)
            self.assertEqual(diagnostics["incomplete_record_count"], 1)
            self.assertTrue(diagnostics["provenance"]["database_read_only_unchanged"])
            self.assertEqual(diagnostics["provenance"]["source_git_blob_sha1"], blob)

    def test_rejects_wrong_source_blob_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "fh6_game_db.sqlite"
            _fixture(database)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--db", str(database),
                    "--output", str(root / "stock.json"),
                    "--report", str(root / "report.json"),
                    "--source-repository", "fixture/repo",
                    "--source-commit", "fixture-commit",
                    "--source-blob-sha1", "0" * 40,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("source Git blob mismatch", completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
