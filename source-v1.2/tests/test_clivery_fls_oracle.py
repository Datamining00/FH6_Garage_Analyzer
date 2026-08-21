from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from fh6garage.fh6_clivery.fls_oracle import (
    FLSOracleError,
    fls_kind_node_dump,
    inspect_fls_project_bytes,
    inspect_fls_project_file,
    iter_fls_kind_nodes,
    load_fls_project_bytes,
    main,
)


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

    def test_loader_preserves_black_box_document_and_hashes(self) -> None:
        raw = make_project()
        artifact = load_fls_project_bytes(raw)
        self.assertEqual(artifact.raw_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(artifact.document["root"]["kind"], "group")
        self.assertEqual(artifact.raw_length, len(raw))
        self.assertGreater(artifact.uncompressed_length, 0)

    def test_kind_node_iterator_reports_exact_json_paths_without_field_mapping(self) -> None:
        artifact = load_fls_project_bytes(make_project())
        nodes = list(iter_fls_kind_nodes(artifact.document))
        self.assertEqual(
            [path for path, _node in nodes],
            [
                ("root",),
                ("root", "children", 0),
                ("root", "children", 1),
                ("root", "children", 1, "children", 0),
            ],
        )
        self.assertEqual([node["kind"] for _path, node in nodes], ["group", "shape", "group", "shape"])

    def test_node_dump_preserves_raw_node_dicts_and_paths(self) -> None:
        artifact = load_fls_project_bytes(make_project())
        dump = fls_kind_node_dump(artifact)
        self.assertEqual(dump["node_count"], 4)
        self.assertEqual(dump["nodes"][1]["path"], ["root", "children", 0])
        self.assertEqual(dump["nodes"][1]["node"], {"kind": "shape", "id": 101, "mask": False})

    def test_cli_can_write_inventory_and_raw_node_dump(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "oracle.3so"
            inventory_path = root / "inventory.json"
            nodes_path = root / "nodes.json"
            source.write_bytes(make_project())
            self.assertEqual(
                main([str(source), "-o", str(inventory_path), "--nodes-output", str(nodes_path)]),
                0,
            )
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
            self.assertEqual(inventory["kind_node_count"], 4)
            self.assertEqual(nodes["node_count"], 4)

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

    def test_real_2997_fls_project_when_available(self) -> None:
        value = os.environ.get("FH6_FLS_3SO_2997")
        if not value or not Path(value).is_file():
            self.skipTest(
                "set FH6_FLS_3SO_2997 to an untouched FLS .3so saved from the SHA-pinned Car 2997 C_livery"
            )

        path = Path(value)
        raw = path.read_bytes()
        inventory = inspect_fls_project_file(path)
        artifact = load_fls_project_bytes(raw)
        nodes = tuple(iter_fls_kind_nodes(artifact.document))

        self.assertTrue(inventory.root_present)
        self.assertGreater(inventory.kind_node_count, 0)
        self.assertEqual(len(nodes), inventory.kind_node_count)
        self.assertIsInstance(artifact.document["root"], dict)
        self.assertIsInstance(artifact.document["root"].get("kind"), str)
        self.assertEqual(inventory.raw_sha256, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
