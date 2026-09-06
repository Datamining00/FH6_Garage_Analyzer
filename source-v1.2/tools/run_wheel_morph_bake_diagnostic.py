from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile


MODES = ("none", "diameter", "width", "combined")


def rim_morph_weights(wheel_diameter_in: float, tire_width_mm: float) -> tuple[float, float]:
    diameter = float(wheel_diameter_in)
    width = float(tire_width_mm)
    if not (diameter > 0.0 and width > 0.0):
        raise ValueError("wheel diameter and tire width must be positive")
    return (diameter - 10.0) / 14.0, (1.0 - width / 1000.0) / 0.9


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_carbin_entry(archive_path: Path, requested: str | None = None) -> str:
    with zipfile.ZipFile(archive_path, "r") as archive:
        entries = [name for name in archive.namelist() if name.casefold().endswith(".carbin")]
    if requested:
        normalized = requested.replace("\\", "/").casefold()
        matches = [name for name in entries if name.replace("\\", "/").casefold() == normalized]
        if len(matches) != 1:
            raise RuntimeError(f"requested carbin not found uniquely in archive: {requested}")
        return matches[0]
    if len(entries) == 1:
        return entries[0]
    stem = archive_path.stem.casefold()
    exact = [name for name in entries if Path(name).name.casefold() == f"{stem}.carbin"]
    if len(exact) == 1:
        return exact[0]
    root = [name for name in entries if "/" not in name.replace("\\", "/").strip("/")]
    if len(root) == 1:
        return root[0]
    shown = ", ".join(entries[:20]) or "<none>"
    raise RuntimeError(f"could not choose one carbin automatically; candidates: {shown}")


def read_glb_json(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise RuntimeError(f"not a GLB file: {path}")
    version = int.from_bytes(data[4:8], "little")
    total = int.from_bytes(data[8:12], "little")
    if version != 2 or total != len(data):
        raise RuntimeError(f"unsupported/truncated GLB: {path}")
    cursor = 12
    document = None
    while cursor + 8 <= total:
        length = int.from_bytes(data[cursor:cursor + 4], "little")
        chunk_type = int.from_bytes(data[cursor + 4:cursor + 8], "little")
        cursor += 8
        if cursor + length > total:
            raise RuntimeError(f"GLB chunk outside file: {path}")
        payload = data[cursor:cursor + length]
        cursor += length
        if chunk_type == 0x4E4F534A:
            document = json.loads(payload.rstrip(b" \x00").decode("utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError(f"GLB has no JSON document: {path}")
    return document


def wheelstyle_aabbs(document: dict) -> list[dict]:
    meshes = document.get("meshes")
    accessors = document.get("accessors")
    if not isinstance(meshes, list) or not isinstance(accessors, list):
        raise RuntimeError("GLB is missing meshes/accessors")
    groups: dict[str, dict] = {}
    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        part_type = str(extras.get("kfps_part_type") or "").casefold()
        if part_type not in {"wheelstyle", "ccarparts_wheelstyle"}:
            continue
        identity = str(extras.get("kfps_instance_identity") or "")
        if not identity:
            raise RuntimeError(f"WheelStyle mesh {mesh_index} has no kfps_instance_identity")
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list) or len(primitives) != 1 or not isinstance(primitives[0], dict):
            raise RuntimeError(f"WheelStyle mesh {mesh_index} is not one-primitive KFPS geometry")
        attrs = primitives[0].get("attributes")
        accessor_index = attrs.get("POSITION") if isinstance(attrs, dict) else None
        if not isinstance(accessor_index, int) or not (0 <= accessor_index < len(accessors)):
            raise RuntimeError(f"WheelStyle mesh {mesh_index} has invalid POSITION accessor")
        accessor = accessors[accessor_index]
        amin = accessor.get("min") if isinstance(accessor, dict) else None
        amax = accessor.get("max") if isinstance(accessor, dict) else None
        if not (isinstance(amin, list) and isinstance(amax, list) and len(amin) == 3 and len(amax) == 3):
            raise RuntimeError(f"WheelStyle POSITION accessor {accessor_index} has no AABB")
        low = [float(value) for value in amin]
        high = [float(value) for value in amax]
        group = groups.setdefault(identity, {"min": low[:], "max": high[:], "mesh_count": 0})
        group["min"] = [min(group["min"][axis], low[axis]) for axis in range(3)]
        group["max"] = [max(group["max"][axis], high[axis]) for axis in range(3)]
        group["mesh_count"] += 1
    if not groups:
        raise RuntimeError("no WheelStyle geometry found in GLB")

    result = []
    for identity, item in groups.items():
        low = item["min"]
        high = item["max"]
        center = [(low[axis] + high[axis]) * 0.5 for axis in range(3)]
        span = [high[axis] - low[axis] for axis in range(3)]
        result.append({
            "instance_identity": identity,
            "mesh_count": item["mesh_count"],
            "min": low,
            "max": high,
            "center": center,
            "span": span,
        })
    result.sort(key=lambda item: (item["center"][2], item["center"][0], item["instance_identity"]))
    if len(result) >= 2:
        min_z = min(item["center"][2] for item in result)
        max_z = max(item["center"][2] for item in result)
        split_z = (min_z + max_z) * 0.5
        for item in result:
            item["axle_from_world_z"] = "front" if item["center"][2] > split_z else "rear"
    return result


def compare_aabbs(baseline: list[dict], candidate: list[dict]) -> list[dict]:
    base_map = {item["instance_identity"]: item for item in baseline}
    candidate_map = {item["instance_identity"]: item for item in candidate}
    if set(base_map) != set(candidate_map):
        raise RuntimeError("WheelStyle instance identities changed between baseline and candidate")
    rows = []
    for identity in sorted(base_map):
        base = base_map[identity]
        current = candidate_map[identity]
        rows.append({
            "instance_identity": identity,
            "baseline_span": base["span"],
            "candidate_span": current["span"],
            "span_delta": [current["span"][axis] - base["span"][axis] for axis in range(3)],
            "baseline_center": base["center"],
            "candidate_center": current["center"],
            "center_delta": [current["center"][axis] - base["center"][axis] for axis in range(3)],
            "axle_from_world_z": base.get("axle_from_world_z"),
        })
    return rows


def _converter_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def run_conversion(
    converter: Path,
    archive: Path,
    carbin_entry: str,
    output: Path,
    mode: str,
    weights: dict[str, float],
) -> dict:
    request = output.with_suffix(".request.json")
    request.write_text(json.dumps({
        "Archive": str(archive),
        "Output": str(output),
        "CarbinEntry": carbin_entry,
        "Entries": [],
    }, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["KFPS_WHEEL_MORPH_MODE"] = mode
    for key, value in weights.items():
        env[key] = format(float(value), ".17g")
    process = subprocess.run(
        [str(converter), "--request", str(request)],
        cwd=str(converter.parent),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    record = {
        "mode": mode,
        "returncode": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "converter_json": _converter_json(process.stdout),
        "output": str(output),
        "request": str(request),
    }
    if process.returncode != 0 or not output.is_file():
        raise RuntimeError(
            f"converter failed for {mode}: returncode={process.returncode}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
    record["wheelstyle_aabbs"] = wheelstyle_aabbs(read_glb_json(output))
    return record


def choose_archive() -> Path | None:
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        selected = filedialog.askopenfilename(
            title="Select FH6 vehicle ZIP",
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
        )
        root.destroy()
    except Exception:
        return None
    return Path(selected) if selected else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only four-way FH6 WheelStyle weighted morph bake diagnostic.")
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument(
        "--converter",
        type=Path,
        default=Path(__file__).resolve().parent / "Kfps.ChassisConverter.exe",
    )
    parser.add_argument("--carbin")
    parser.add_argument("--front-width-mm", type=float, required=True)
    parser.add_argument("--front-wheel-diameter-in", type=float, required=True)
    parser.add_argument("--rear-width-mm", type=float, required=True)
    parser.add_argument("--rear-wheel-diameter-in", type=float, required=True)
    parser.add_argument("--spec-basis", default="user-supplied diagnostic candidate")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    archive = args.archive or choose_archive()
    if archive is None:
        parser.error("vehicle ZIP was not selected")
    archive = archive.expanduser().resolve()
    converter = args.converter.expanduser().resolve()
    if not archive.is_file():
        parser.error(f"vehicle ZIP does not exist: {archive}")
    if not converter.is_file():
        parser.error(f"diagnostic converter does not exist: {converter}")

    front_diameter, front_width = rim_morph_weights(args.front_wheel_diameter_in, args.front_width_mm)
    rear_diameter, rear_width = rim_morph_weights(args.rear_wheel_diameter_in, args.rear_width_mm)
    weights = {
        "KFPS_WHEEL_MORPH_FRONT_DIAMETER": front_diameter,
        "KFPS_WHEEL_MORPH_FRONT_WIDTH": front_width,
        "KFPS_WHEEL_MORPH_REAR_DIAMETER": rear_diameter,
        "KFPS_WHEEL_MORPH_REAR_WIDTH": rear_width,
    }

    carbin = resolve_carbin_entry(archive, args.carbin)
    if args.output_dir:
        output_dir = args.output_dir.expanduser().resolve()
    else:
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = local / "FH6 Assistant" / "Diagnostics" / f"{archive.stem}_wheel_morph_bake_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=False)
    if output_dir == archive.parent or archive.parent in output_dir.parents:
        raise RuntimeError("output directory must not be inside the source archive directory")

    before_sha = sha256_file(archive)
    conversions = {}
    for mode in MODES:
        output = output_dir / f"{archive.stem}_wheel_{mode}.glb"
        conversions[mode] = run_conversion(converter, archive, carbin, output, mode, weights)
    after_sha = sha256_file(archive)
    if before_sha != after_sha:
        raise RuntimeError("source vehicle ZIP SHA-256 changed; refusing diagnostic result")

    baseline = conversions["none"]["wheelstyle_aabbs"]
    comparisons = {
        mode: compare_aabbs(baseline, conversions[mode]["wheelstyle_aabbs"])
        for mode in ("diameter", "width", "combined")
    }
    report = {
        "format": "fh6_wheel_morph_four_way_diagnostic_v1",
        "archive": str(archive),
        "archive_sha256_before": before_sha,
        "archive_sha256_after": after_sha,
        "source_archive_unchanged": before_sha == after_sha,
        "carbin_entry": carbin,
        "converter": str(converter),
        "spec_basis": args.spec_basis,
        "input_spec": {
            "front_tire_width_mm": args.front_width_mm,
            "front_wheel_diameter_in": args.front_wheel_diameter_in,
            "rear_tire_width_mm": args.rear_width_mm,
            "rear_wheel_diameter_in": args.rear_wheel_diameter_in,
        },
        "derived_rim_weights": {
            "front": {"diameter": front_diameter, "width": front_width, "scale_x": 1.0},
            "rear": {"diameter": rear_diameter, "width": rear_width, "scale_x": 1.0},
        },
        "conversions": conversions,
        "comparisons_vs_baseline": comparisons,
    }
    report_path = output_dir / "wheel_morph_four_way_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
