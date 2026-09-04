from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .near_lod import (
    NORMALIZATION_REVISION as NEAR_LOD_NORMALIZATION_REVISION,
    NearLodNormalizationError,
    discard_near_lod_archive,
    prepare_near_lod_archive,
)
from .neutral_geometry import NEUTRAL_GEOMETRY_REVISION, NeutralGeometryError, annotate_neutral_geometry
from .vehicle_assets import VehicleAsset

CONVERTER_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"
CONVERTER_BLOB_SHA1 = "7d3f83ce4d787c752a01729d1a5a6b81ca5cc800"
CONVERTER_URL = (
    "https://raw.githubusercontent.com/heyitshestia/kloudys-forza-painter-suite/"
    f"{CONVERTER_COMMIT}/tools/livery/chassis-converter/bin/win-x64/Kfps.ChassisConverter.exe"
)


class ChassisConverterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversionResult:
    output_path: str
    diagnostics: dict


def app_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / "FH6 Assistant" / "3d_preview" if base else Path.home() / ".fh6_assistant" / "3d_preview"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cache_dir() -> Path:
    path = app_data_root() / "glb"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tools_dir() -> Path:
    path = app_data_root() / "tools"
    path.mkdir(parents=True, exist_ok=True)
    return path


def converter_path() -> Path:
    return tools_dir() / "Kfps.ChassisConverter.exe"


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def converter_is_valid(path: Path | None = None) -> bool:
    target = path or converter_path()
    try:
        data = target.read_bytes()
    except OSError:
        return False
    return len(data) >= 1024 * 1024 and _git_blob_sha1(data).lower() == CONVERTER_BLOB_SHA1.lower()


def ensure_converter(progress: Callable[[str], None] | None = None) -> Path:
    target = converter_path()
    if converter_is_valid(target):
        return target
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        raise ChassisConverterError(f"Invalid converter could not be replaced: {exc}") from exc
    if progress:
        progress("3D 변환기 준비 중...")
    temp = target.with_suffix(".exe.download")
    try:
        request = urllib.request.Request(CONVERTER_URL, headers={"User-Agent": "FH6-Assistant-3D-Preview/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                out.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ChassisConverterError(f"Could not download the pinned chassis converter: {exc}") from exc
    try:
        data = temp.read_bytes()
    except OSError as exc:
        raise ChassisConverterError(f"Downloaded converter could not be read: {exc}") from exc
    actual = _git_blob_sha1(data)
    if actual.lower() != CONVERTER_BLOB_SHA1.lower():
        temp.unlink(missing_ok=True)
        raise ChassisConverterError(
            f"Downloaded converter failed integrity verification: expected {CONVERTER_BLOB_SHA1}, got {actual}."
        )
    temp.replace(target)
    return target


def _safe_output_for(asset: VehicleAsset) -> Path:
    safe_model = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in asset.model_code)
    return cache_dir() / f"car_{asset.car_id}_{safe_model}.glb"


def _assert_output_separate_from_game(asset: VehicleAsset, output: Path) -> None:
    archive = Path(asset.archive_path).resolve()
    output = output.resolve()
    try:
        if output == archive or output.is_relative_to(archive.parent):
            raise ChassisConverterError("Derived GLB path overlaps the FH6 game-data directory.")
    except AttributeError:
        prefix = str(archive.parent).casefold().rstrip("\\/") + os.sep
        if str(output).casefold().startswith(prefix):
            raise ChassisConverterError("Derived GLB path overlaps the FH6 game-data directory.")


def _source_signature(asset: VehicleAsset, carbin_entry: str) -> dict:
    source = Path(asset.archive_path)
    stat = source.stat()
    return {
        "source_archive": str(source.resolve()),
        "source_size": int(stat.st_size),
        "source_mtime_ns": int(stat.st_mtime_ns),
        "carbin_entry": carbin_entry,
        "near_lod_revision": int(NEAR_LOD_NORMALIZATION_REVISION),
        "neutral_geometry_revision": int(NEUTRAL_GEOMETRY_REVISION),
        "converter_commit": CONVERTER_COMMIT,
    }


def _cached_result(asset: VehicleAsset, carbin_entry: str) -> ConversionResult | None:
    output = _safe_output_for(asset)
    sidecar = output.with_suffix(".json")
    if not output.is_file() or not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        signature = _source_signature(asset, carbin_entry)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("signature") != signature:
        return None
    try:
        if output.read_bytes()[:4] != b"glTF":
            return None
    except OSError:
        return None
    return ConversionResult(str(output), data)


def convert_vehicle(
    asset: VehicleAsset,
    progress: Callable[[str], None] | None = None,
    *,
    carbin_entry: str,
) -> ConversionResult:
    if os.name != "nt":
        raise ChassisConverterError("FH6 chassis conversion is available on Windows x64 only.")
    if carbin_entry not in asset.carbin_entries:
        raise ChassisConverterError(f"Selected carbin scene is not present in {asset.archive_name}: {carbin_entry}")
    if not Path(asset.archive_path).is_file():
        raise ChassisConverterError(f"Vehicle archive no longer exists: {asset.archive_path}")

    cached = _cached_result(asset, carbin_entry)
    if cached is not None:
        if progress:
            progress("기존 3D 차량 캐시 사용 중...")
        return cached

    helper = ensure_converter(progress)
    output = _safe_output_for(asset)
    _assert_output_separate_from_game(asset, output)
    output.parent.mkdir(parents=True, exist_ok=True)

    source_archive = Path(asset.archive_path).resolve()
    try:
        normalized_archive, normalization = prepare_near_lod_archive(
            source_archive,
            carbin_entry,
            asset.model_code,
            app_data_root(),
            progress=progress,
        )
    except (OSError, ValueError, NearLodNormalizationError) as exc:
        raise ChassisConverterError(f"Near-LOD preparation failed: {exc}") from exc

    request = {
        "archive": str(normalized_archive.resolve()),
        "output": str(output.resolve()),
        "carbin_entry": carbin_entry,
        "entries": [],
    }
    request_dir = app_data_root() / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    fd, request_name = tempfile.mkstemp(prefix=f"car_{asset.car_id}_", suffix=".json", dir=request_dir)
    os.close(fd)
    request_path = Path(request_name)
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    completed = None
    neutral_summary: dict = {}
    try:
        if progress:
            progress(f"Car ID {asset.car_id} 3D 변환 중...")
        env = os.environ.copy()
        env["KFPS_CHASSIS_DIAGNOSTICS"] = "1"
        completed = subprocess.run(
            [str(helper), "--request", str(request_path)],
            cwd=str(app_data_root()),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0 and output.is_file():
            try:
                neutral_summary = annotate_neutral_geometry(output, normalized_archive, carbin_entry).as_dict()
            except (OSError, ValueError, NeutralGeometryError) as exc:
                try:
                    output.unlink(missing_ok=True)
                except OSError:
                    pass
                raise ChassisConverterError(
                    "Neutral geometry classification failed; derived GLB was discarded. " + str(exc)
                ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ChassisConverterError("Vehicle conversion exceeded the 5-minute timeout.") from exc
    except OSError as exc:
        raise ChassisConverterError(f"Could not start Kfps.ChassisConverter.exe: {exc}") from exc
    finally:
        try:
            request_path.unlink(missing_ok=True)
        except OSError:
            pass
        discard_near_lod_archive(normalized_archive)

    if completed is None or completed.returncode != 0:
        details = ((completed.stderr or completed.stdout) if completed is not None else "Unknown converter failure").strip()
        raise ChassisConverterError(f"Chassis conversion failed:\n{details}")
    if not output.is_file():
        raise ChassisConverterError("Converter reported success but no GLB was created.")
    try:
        header = output.read_bytes()[:12]
    except OSError as exc:
        raise ChassisConverterError(f"Generated GLB could not be reopened: {exc}") from exc
    if len(header) < 12 or header[:4] != b"glTF":
        output.unlink(missing_ok=True)
        raise ChassisConverterError("Generated file is not a valid GLB container.")

    converter_diagnostics: dict = {}
    stdout = completed.stdout.strip()
    if stdout:
        try:
            candidate = json.loads(stdout)
        except json.JSONDecodeError:
            candidate = None
            first, last = stdout.find("{"), stdout.rfind("}")
            if first >= 0 and last > first:
                try:
                    candidate = json.loads(stdout[first:last + 1])
                except json.JSONDecodeError:
                    candidate = None
        if isinstance(candidate, dict):
            converter_diagnostics = candidate
    try:
        unresolved_required = int(converter_diagnostics.get("unresolved_instance_count", 0) or 0)
    except (TypeError, ValueError):
        unresolved_required = 0
    if unresolved_required > 0:
        output.unlink(missing_ok=True)
        raise ChassisConverterError(
            f"Chassis scene has {unresolved_required} unresolved required model instance(s); refusing a partial GLB."
        )

    diagnostics = {
        "format": "fh6_assistant_3d_conversion_v1",
        "signature": _source_signature(asset, carbin_entry),
        "game_data_modified": False,
        "neutral_geometry": neutral_summary,
        "normalization": asdict(normalization),
        "converter": converter_diagnostics,
        "glb_size": int(output.stat().st_size),
    }
    output.with_suffix(".json").write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress("3D 차량 변환 완료")
    return ConversionResult(str(output), diagnostics)
