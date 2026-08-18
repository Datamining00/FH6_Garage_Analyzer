from __future__ import annotations

import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_4_patch import _build_analysis_panel


class V14LiveryInfoPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _container() -> bytes:
        counts = (1, 2, 3, 4, 5, 6, 0, 8, 0, 10, 11)
        payload = (
            b"vlrc"
            + b"\x00" * 24
            + b"gyvl"
            + b"\x22" * 48
            + b"yrvl"
            + struct.pack("<11I", *counts)
            + b"\x00" * 16
        )
        compressed = zlib.compress(payload)
        return struct.pack("<II", len(compressed), len(payload)) + compressed

    def test_analysis_panel_renders_eleven_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            livery_path = root / "C_livery"
            livery_path.write_bytes(self._container())
            record = LiveryRecord(
                container_name="Livery_1_test",
                container_path=root,
                kind="Livery",
                header=HeaderInfo(name="test", decal_count=50, car_id=1),
                livery_path=livery_path,
            )
            panel = _build_analysis_panel(record)
            table = panel.findChild(QTableWidget)
            self.assertIsNotNone(table)
            self.assertEqual(table.rowCount(), 11)
            labels = [label.text() for label in panel.findChildren(QLabel)]
            self.assertTrue(any("50" in text for text in labels))
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
