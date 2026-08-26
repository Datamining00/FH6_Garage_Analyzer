from __future__ import annotations

import unittest

import fh6garage
from fh6garage.version import PRODUCT_NAME, SIDEBAR_VERSION, VERSION, WINDOW_TITLE


class VersionContractTests(unittest.TestCase):
    def test_package_and_runtime_version_share_one_value(self) -> None:
        self.assertEqual(fh6garage.__version__, VERSION)

    def test_display_labels_are_derived_from_version(self) -> None:
        self.assertEqual(WINDOW_TITLE, f"{PRODUCT_NAME} v{VERSION}")
        self.assertEqual(SIDEBAR_VERSION, f"v{VERSION}\nLIVERY & TUNING")


if __name__ == "__main__":
    unittest.main()
