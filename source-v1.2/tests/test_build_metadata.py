from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.build_metadata import (
    PORTABLE_DIR_NAME,
    PORTABLE_SPEC,
    STANDARD_NAME,
    STANDARD_SPEC,
    build_metadata,
)
from fh6garage.version import VERSION, WINDOW_TITLE


ROOT = Path(__file__).resolve().parents[1]


class BuildMetadataContractTests(unittest.TestCase):
    def test_distribution_names_follow_runtime_version(self) -> None:
        self.assertEqual(STANDARD_NAME, WINDOW_TITLE)
        self.assertEqual(PORTABLE_DIR_NAME, f"{WINDOW_TITLE} Portable")

    def test_specs_exist_and_use_shared_names(self) -> None:
        standard = (ROOT / STANDARD_SPEC).read_text(encoding="utf-8")
        portable = (ROOT / PORTABLE_SPEC).read_text(encoding="utf-8")
        self.assertIn("name=STANDARD_NAME", standard)
        self.assertIn("name=STANDARD_NAME", portable)
        self.assertIn("name=PORTABLE_DIR_NAME", portable)

    def test_windows_metadata_matches_runtime_version(self) -> None:
        metadata = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        numeric = VERSION.split("-", 1)[0]
        parts = [int(part) for part in numeric.split(".")]
        four_part = tuple((parts + [0, 0, 0, 0])[:4])
        self.assertIn(f"filevers={four_part}", metadata)
        self.assertIn(f"prodvers={four_part}", metadata)
        self.assertIn(f"ProductVersion', '{VERSION}'", metadata)
        self.assertIn(f"OriginalFilename', '{STANDARD_NAME}.exe'", metadata)

    def test_powershell_receives_all_required_fields(self) -> None:
        self.assertEqual(
            set(build_metadata()),
            {"standard_name", "portable_dir_name", "standard_spec", "portable_spec"},
        )


if __name__ == "__main__":
    unittest.main()
