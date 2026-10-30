#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sort_vehicle_ids(ids: set[str] | list[str]) -> list[str]:
    def sort_key(value: str) -> tuple[int, int | str, str]:
        if value.isdigit():
            return (0, int(value), value)
        return (1, value, value)

    return sorted(ids, key=sort_key)


def normalize(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source_meta = source.get("_meta") if isinstance(source.get("_meta"), dict) else {}
    vehicles: dict[str, Any] = {}
    seen_ids: set[str] = set()

    for name, record in source.items():
        if name == "_meta":
            continue

        if not isinstance(record, dict):
            raise ValueError(f"Vehicle record must be an object: {name!r}")

        vehicle_id = record.get("id")
        if vehicle_id is None:
            raise ValueError(f"Vehicle record is missing id: {name!r}")

        vehicle_id = str(vehicle_id)
        if vehicle_id in seen_ids:
            raise ValueError(f"Duplicate vehicle id: {vehicle_id}")
        seen_ids.add(vehicle_id)

        normalized_record: dict[str, Any] = {
            "name": name,
            "id": vehicle_id,
        }
        for key in sorted(k for k in record if k != "id"):
            normalized_record[key] = record[key]

        vehicles[vehicle_id] = normalized_record

    vehicles = {vehicle_id: vehicles[vehicle_id] for vehicle_id in sort_vehicle_ids(list(vehicles))}
    return source_meta, vehicles


def field_diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    missing = object()

    for field in sorted(set(old) | set(new)):
        old_value = old.get(field, missing)
        new_value = new.get(field, missing)

        if old_value == new_value:
            continue

        result[field] = {
            "old": None if old_value is missing else old_value,
            "new": None if new_value is missing else new_value,
            "old_missing": old_value is missing,
            "new_missing": new_value is missing,
        }

    return result


def build_diff(
    old_vehicles: dict[str, Any],
    new_vehicles: dict[str, Any],
) -> dict[str, Any]:
    old_ids = set(old_vehicles)
    new_ids = set(new_vehicles)

    added_ids = sort_vehicle_ids(list(new_ids - old_ids))
    removed_ids = sort_vehicle_ids(list(old_ids - new_ids))
    common_ids = sort_vehicle_ids(list(old_ids & new_ids))

    added = {vehicle_id: new_vehicles[vehicle_id] for vehicle_id in added_ids}
    removed = {vehicle_id: old_vehicles[vehicle_id] for vehicle_id in removed_ids}
    modified: dict[str, Any] = {}

    for vehicle_id in common_ids:
        changes = field_diff(old_vehicles[vehicle_id], new_vehicles[vehicle_id])
        if changes:
            modified[vehicle_id] = {
                "name_before": old_vehicles[vehicle_id].get("name"),
                "name_after": new_vehicles[vehicle_id].get("name"),
                "fields": changes,
            }

    return {
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
        },
        "added": added,
        "removed": removed,
        "modified": modified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mirror, normalize, and diff FH6 vehicle data from the source Gist."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--root", default=Path("data/fh6"), type=Path)
    parser.add_argument("--timestamp", help="UTC ISO timestamp override for deterministic tests")
    args = parser.parse_args()

    if args.timestamp:
        now = datetime.fromisoformat(args.timestamp.replace("Z", "+00:00"))
    else:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    now = now.astimezone(timezone.utc)
    timestamp_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    timestamp_path = now.strftime("%Y/%m/%d/%H%M%SZ")

    source_bytes = args.source.read_bytes()
    source_sha256 = sha256_bytes(source_bytes)
    source = json.loads(source_bytes.decode("utf-8"))

    if not isinstance(source, dict):
        raise ValueError("Top-level FH6 vehicle data must be a JSON object")

    source_meta, vehicles = normalize(source)
    normalized_sha256 = sha256_bytes(canonical_bytes(vehicles))

    root: Path = args.root
    mirror_path = root / "mirror" / "FH6_Vehicle_Data.json"
    latest_path = root / "normalized" / "latest.json"
    previous_path = root / "normalized" / "previous.json"
    snapshot_path = (
        root
        / "snapshots"
        / "by-hash"
        / f"{normalized_sha256}.json"
    )
    diff_latest_path = root / "diffs" / "latest.json"
    diff_history_path = (
        root
        / "diffs"
        / "history"
        / f"{timestamp_path}.json"
    )
    run_path = root / "runs" / f"{timestamp_path}.json"
    state_path = root / "state.json"

    old_snapshot: dict[str, Any] | None = None
    if latest_path.exists():
        old_snapshot = load_json(latest_path)

    old_vehicles = (
        old_snapshot.get("vehicles", {})
        if isinstance(old_snapshot, dict)
        else {}
    )
    previous_normalized_sha256 = (
        old_snapshot.get("normalized_sha256")
        if isinstance(old_snapshot, dict)
        else None
    )

    diff = build_diff(old_vehicles, vehicles)
    changed = previous_normalized_sha256 != normalized_sha256

    normalized_snapshot = {
        "schema": "fh6_vehicle_normalized_snapshot_v1",
        "generated_at": timestamp_iso,
        "source": {
            "kind": "gist_mirror",
            "gist_id": "30fe44689fad7ba5e99e2381927b7730",
            "filename": "FH6_Vehicle_Data.json",
            "source_sha256": source_sha256,
        },
        "normalized_sha256": normalized_sha256,
        "vehicle_count": len(vehicles),
        "source_meta": source_meta,
        "vehicles": vehicles,
    }

    diff_document = {
        "schema": "fh6_vehicle_field_diff_v1",
        "generated_at": timestamp_iso,
        "previous_normalized_sha256": previous_normalized_sha256,
        "current_normalized_sha256": normalized_sha256,
        "changed": changed,
        **diff,
    }

    # Exact byte-for-byte mirror of the Gist file.
    mirror_path.parent.mkdir(parents=True, exist_ok=True)
    mirror_path.write_bytes(source_bytes)

    # Keep previous/latest normalized states for fast comparisons.
    if old_snapshot is not None:
        write_json(previous_path, old_snapshot)
    write_json(latest_path, normalized_snapshot)

    # Full snapshots are content-addressed. Identical data reuses the same file,
    # avoiding three ~150 KB copies every day when the source is unchanged.
    if not snapshot_path.exists():
        write_json(snapshot_path, normalized_snapshot)

    # A small diff and run manifest are retained for every execution.
    write_json(diff_latest_path, diff_document)
    write_json(diff_history_path, diff_document)

    run_document = {
        "schema": "fh6_vehicle_sync_run_v1",
        "executed_at": timestamp_iso,
        "source_sha256": source_sha256,
        "normalized_sha256": normalized_sha256,
        "vehicle_count": len(vehicles),
        "changed": changed,
        "snapshot": snapshot_path.as_posix(),
        "diff": diff_history_path.as_posix(),
        "diff_counts": diff["counts"],
    }
    write_json(run_path, run_document)

    state_document = {
        "schema": "fh6_vehicle_sync_state_v1",
        "last_run_at": timestamp_iso,
        "source_sha256": source_sha256,
        "normalized_sha256": normalized_sha256,
        "vehicle_count": len(vehicles),
        "last_snapshot": snapshot_path.as_posix(),
        "last_diff": diff_history_path.as_posix(),
        "last_run": run_path.as_posix(),
        "diff_counts": diff["counts"],
    }
    write_json(state_path, state_document)

    print(
        json.dumps(
            {
                "executed_at": timestamp_iso,
                "vehicle_count": len(vehicles),
                "changed": changed,
                "normalized_sha256": normalized_sha256,
                "diff_counts": diff["counts"],
                "snapshot": snapshot_path.as_posix(),
                "run": run_path.as_posix(),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
