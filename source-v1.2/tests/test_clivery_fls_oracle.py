from __future__ import annotations

import gzip
import json
import unittest

from fh6garage.fh6_clivery.fls_oracle import FLSOracleError, inspect_fls_project_bytes


def make_project() -> bytes:
    document = {
        "version": 1,
        "metadata": {"name": "oracle"},
        "root": {
            "kind": "group",
            "children": [
                {"kind": "shape", "id": 101, "mask": False},
                {
                    "kind": "group",
                    "children": [
                        {"kind": "shape", "id": 102, "mask": True},
                    ],
                },
            ],
        },
    }
    return gzip.compress(json.dumps(document, separators=(",", ":")).encode("utf-8"))


class FLSProjectOracleTests(unittest.TestCase):
    def test_documented_3so_container_is_inventoried_without_schema_guessing(self) -> None:
        result = inspect_fls_project_bytes(make_project())
        self.assertTrue(result.root_present)
        self.assertEqual(result.kind_node_count, 4)
        self.assertEqual(dict(result.kind_counts), {"group": 2, "shape": 2})
        self.assertEqual(result.candidate_child_keys, ("children",))
        signatures = {(kind, keys): count for kind, keys, count in result.node_key_signatures}
        self.assertEqual(signatures[("group", ("children", "kind"))], 2)
        self.assertEqual(signatures[("shape", ("id", "kind", "mask"))], 2)

    def test_inventory_is_deterministic_for_same_bytes(self) -> None:
        raw = make_project()
        first = inspect_fls_project_bytes(raw)
        second = inspect_fls_project_bytes(raw)
        self.assertEqual(first, second)
        self.assertEqual(first.to_json(), second.to_json())

    def test_non_gzip_input_is_rejected(self) -> None:
        with self.assertRaises(FLSOracleError):
            inspect_fls_project_bytes(b"not gzip")

    def test_non_json_payload_is_rejected(self) -> None:
        with self.assertRaises(FLSOracleError):
            inspect_fls_project_bytes(gzip.compress(b"not json"))

    def test_missing_documented_root_is_rejected(self) -> None:
        raw = gzip.compress(json.dumps({"version": 1}).encode("utf-8"))
        with self.assertRaises(FLSOracleError):
            inspect_fls_project_bytes(raw)


if __name__ == "__main__":
    unittest.main()
