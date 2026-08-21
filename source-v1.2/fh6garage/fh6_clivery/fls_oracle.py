from __future__ import annotations

from dataclasses import dataclass
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


FLS_PROJECT_ORACLE_FORMAT_ID = "fh6-assistant-fls-project-inventory-v1"


class FLSOracleError(ValueError):
    """Raised when an FLS .3so black-box oracle artifact cannot be inspected safely."""


@dataclass(frozen=True)
class FLSProjectInventory:
    raw_sha256: str
    uncompressed_sha256: str
    raw_length: int
    uncompressed_length: int
    top_level_keys: tuple[str, ...]
    root_present: bool
    kind_node_count: int
    kind_counts: tuple[tuple[str, int], ...]
    node_key_signatures: tuple[tuple[str, tuple[str, ...], int], ...]
    candidate_child_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "format": FLS_PROJECT_ORACLE_FORMAT_ID,
            "raw_sha256": self.raw_sha256,
            "uncompressed_sha256": self.uncompressed_sha256,
            "raw_length": self.raw_length,
            "uncompressed_length": self.uncompressed_length,
            "top_level_keys": list(self.top_level_keys),
            "root_present": self.root_present,
            "kind_node_count": self.kind_node_count,
            "kind_counts": {kind: count for kind, count in self.kind_counts},
            "node_key_signatures": [
                {"kind": kind, "keys": list(keys), "count": count}
                for kind, keys, count in self.node_key_signatures
            ],
            "candidate_child_keys": list(self.candidate_child_keys),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _contains_kind_node(value: Any) -> bool:
    if isinstance(value, dict):
        if isinstance(value.get("kind"), str):
            return True
        return any(_contains_kind_node(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_kind_node(child) for child in value)
    return False


def _inventory_kind_nodes(document: dict[str, Any]) -> tuple[
    int,
    tuple[tuple[str, int], ...],
    tuple[tuple[str, tuple[str, ...], int], ...],
    tuple[str, ...],
]:
    kind_counts: dict[str, int] = {}
    signatures: dict[tuple[str, tuple[str, ...]], int] = {}
    child_keys: set[str] = set()
    node_count = 0

    def walk(value: Any) -> None:
        nonlocal node_count
        if isinstance(value, dict):
            kind = value.get("kind")
            if isinstance(kind, str):
                node_count += 1
                kind_counts[kind] = kind_counts.get(kind, 0) + 1
                keys = tuple(sorted(str(key) for key in value.keys()))
                signature = (kind, keys)
                signatures[signature] = signatures.get(signature, 0) + 1
                for key, child in value.items():
                    if key == "kind":
                        continue
                    if _contains_kind_node(child):
                        child_keys.add(str(key))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(document)
    sorted_counts = tuple(sorted(kind_counts.items(), key=lambda item: item[0]))
    sorted_signatures = tuple(
        (kind, keys, count)
        for (kind, keys), count in sorted(
            signatures.items(), key=lambda item: (item[0][0], item[0][1])
        )
    )
    return node_count, sorted_counts, sorted_signatures, tuple(sorted(child_keys))


def inspect_fls_project_bytes(raw: bytes | bytearray | memoryview) -> FLSProjectInventory:
    """Inspect a documented FLS `.3so` project without assuming its scene-node schema.

    Public FLS documentation describes `.3so` as a gzip-wrapped editor project JSON
    whose document contains a recursive `root` scene tree of kind-discriminated
    layer nodes. This function intentionally stops at deterministic schema inventory;
    semantic field mapping is deferred until a real oracle artifact is observed.
    """
    data = bytes(raw)
    if not data:
        raise FLSOracleError("FLS .3so artifact is empty")

    try:
        payload = gzip.decompress(data)
    except (OSError, EOFError) as exc:
        raise FLSOracleError(f"FLS .3so gzip payload could not be decompressed: {exc}") from exc

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FLSOracleError("FLS .3so project payload is not UTF-8 JSON") from exc

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FLSOracleError(f"FLS .3so project payload is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise FLSOracleError("FLS .3so project JSON must be an object at the top level")
    if "root" not in document:
        raise FLSOracleError("FLS .3so project JSON does not contain the documented 'root' scene tree")

    node_count, kind_counts, signatures, child_keys = _inventory_kind_nodes(document)
    return FLSProjectInventory(
        raw_sha256=hashlib.sha256(data).hexdigest(),
        uncompressed_sha256=hashlib.sha256(payload).hexdigest(),
        raw_length=len(data),
        uncompressed_length=len(payload),
        top_level_keys=tuple(sorted(str(key) for key in document.keys())),
        root_present=True,
        kind_node_count=node_count,
        kind_counts=kind_counts,
        node_key_signatures=signatures,
        candidate_child_keys=child_keys,
    )


def inspect_fls_project_file(path: str | Path) -> FLSProjectInventory:
    return inspect_fls_project_bytes(Path(path).read_bytes())


def inspect_fls_project_file_to_json(path: str | Path, *, indent: int = 2) -> str:
    return inspect_fls_project_file(path).to_json(indent=indent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect an FLS .3so project as a black-box semantic-oracle artifact"
    )
    parser.add_argument("source", type=Path, help="FLS .3so project file")
    parser.add_argument("-o", "--output", type=Path, help="write inventory JSON to this file")
    args = parser.parse_args(argv)

    text = inspect_fls_project_file(args.source).to_json() + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
