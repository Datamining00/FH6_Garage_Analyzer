from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .vehicle_index import VehicleAsset
from .near_lod_archive import (
    NORMALIZATION_REVISION as NEAR_LOD_NORMALIZATION_REVISION,
    NearLodNormalizationError,
    discard_near_lod_archive,
    prepare_near_lod_archive,
)

from .neutral_geometry import NEUTRAL_GEOMETRY_REVISION, NeutralGeometryError, annotate_neutral_geometry
from .wheel_visibility import (
    WHEEL_VISIBILITY_REVISION,
    WheelVisibilityError,
    apply_neutral_wheel_visibility,
)

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
    helper_path: str
    diagnostics: dict


def app_data_root() -> Path:
    """Persistent root for required pinned third-party runtime/tools only."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base) / "FH6GarageAnalyzer" / "preview3d_runtime"
    else:
        root = Path.home() / ".fh6garageanalyzer" / "preview3d_runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cache_dir() -> Path:
    path = app_data_root() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tools_dir() -> Path:
    path = app_data_root() / "tools"
    path.mkdir(parents=True, exist_ok=True)
    return path


def converter_path() -> Path:
    return tools_dir() / "Kfps.ChassisConverter.exe"


def _git_blob_sha1(data: bytes) -> str:
    prefix = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(prefix + data).hexdigest()


def converter_is_valid(path: Path | None = None) -> bool:
    target = path or converter_path()
    try:
        data = target.read_bytes()
    except OSError:
        return False
    if len(data) < 1024 * 1024:
        return False
    return _git_blob_sha1(data).lower() == CONVERTER_BLOB_SHA1.lower()


def ensure_converter(progress: Callable[[str], None] | None = None) -> Path:
    target = converter_path()
    if converter_is_valid(target):
        return target

    if target.exists():
        try:
            target.unlink()
        except OSError as exc:
            raise ChassisConverterError(f"Invalid converter exists but could not be replaced: {exc}") from exc

    if progress:
        progress("Downloading the pinned KFPS chassis converter (about 37 MB)...")

    temp = target.with_suffix(".exe.download")
    try:
        request = urllib.request.Request(
            CONVERTER_URL,
            headers={"User-Agent": "FH6-Livery-3D-Viewer-PoC/0.2"},
        )
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ChassisConverterError(
            "Could not download Kfps.ChassisConverter.exe from the pinned upstream source. "
            f"Network error: {exc}"
        ) from exc

    try:
        data = temp.read_bytes()
    except OSError as exc:
        raise ChassisConverterError(f"Downloaded converter could not be read: {exc}") from exc

    actual = _git_blob_sha1(data)
    if actual.lower() != CONVERTER_BLOB_SHA1.lower():
        temp.unlink(missing_ok=True)
        raise ChassisConverterError(
            "Downloaded converter failed integrity verification. "
            f"Expected Git blob {CONVERTER_BLOB_SHA1}, got {actual}."
        )

    temp.replace(target)
    if progress:
        progress("Converter downloaded and integrity-verified.")
    return target


def _safe_output_for(asset: VehicleAsset, work_root: Path | None = None) -> Path:
    safe_model = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in asset.model_code)
    root = Path(work_root) if work_root is not None else cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"car_{asset.car_id}_{safe_model}.glb"


def _assert_output_separate_from_game(asset: VehicleAsset, output: Path) -> None:
    archive = Path(asset.archive_path).resolve()
    output = output.resolve()
    # Output must never be the archive itself or anywhere inside the archive's directory tree.
    try:
        if output == archive or output.is_relative_to(archive.parent):
            raise ChassisConverterError(
                "Safety check refused conversion because the output path overlaps the FH6 game data directory."
            )
    except AttributeError:
        archive_parent = str(archive.parent).casefold().rstrip("\\/") + os.sep
        if str(output).casefold().startswith(archive_parent):
            raise ChassisConverterError(
                "Safety check refused conversion because the output path overlaps the FH6 game data directory."
            )


def convert_vehicle(
    asset: VehicleAsset,
    progress: Callable[[str], None] | None = None,
    *,
    carbin_entry: str | None = None,
    work_root: str | Path | None = None,
) -> ConversionResult:
    if os.name != "nt":
        raise ChassisConverterError("The bundled conversion workflow is Windows x64 only.")
    if not asset.carbin_entries:
        raise ChassisConverterError("The selected vehicle archive has no .carbin scene entry.")
    if not Path(asset.archive_path).is_file():
        raise ChassisConverterError(f"Vehicle archive no longer exists: {asset.archive_path}")

    helper = ensure_converter(progress)
    transient_root = Path(work_root) if work_root is not None else cache_dir()
    transient_root.mkdir(parents=True, exist_ok=True)
    output = _safe_output_for(asset, transient_root)
    _assert_output_separate_from_game(asset, output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if carbin_entry is None:
        if len(asset.carbin_entries) != 1:
            raise ChassisConverterError(
                "The vehicle archive has multiple carbin scenes; an explicit scene selection is required."
            )
        carbin_entry = asset.carbin_entries[0]
    if carbin_entry not in asset.carbin_entries:
        raise ChassisConverterError(f"Selected carbin scene is not indexed in this archive: {carbin_entry}")
    source_archive = Path(asset.archive_path).resolve()
    try:
        normalized_archive, normalization = prepare_near_lod_archive(
            source_archive,
            carbin_entry,
            asset.model_code,
            transient_root,
            progress=progress,
        )
    except (OSError, ValueError, NearLodNormalizationError) as exc:
        raise ChassisConverterError(f"Near-LOD assembly preparation failed: {exc}") from exc

    # The pinned converter reads only this LocalAppData derivative.  The original FH6 archive
    # was opened read-only by prepare_near_lod_archive and is never passed to a write path.
    request = {
        "archive": str(normalized_archive.resolve()),
        "output": str(output.resolve()),
        "carbin_entry": carbin_entry,
        "entries": [],
    }

    request_dir = transient_root / "requests"
    try:
        request_dir.mkdir(parents=True, exist_ok=True)
        fd, request_name = tempfile.mkstemp(prefix=f"car_{asset.car_id}_", suffix=".json", dir=request_dir)
        os.close(fd)
        request_path = Path(request_name)
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    except Exception:
        discard_near_lod_archive(normalized_archive)
        raise

    if progress:
        progress(f"Converting Car ID {asset.car_id} ({asset.model_code}) from a LocalAppData near-LOD derivative of read-only game data...")

    env = os.environ.copy()
    env["KFPS_CHASSIS_DIAGNOSTICS"] = "1"
    wheel_visibility_summary: dict = {}
    wheel_visibility_error: str | None = None
    neutral_geometry_summary: dict = {}
    neutral_geometry_error: str | None = None
    try:
        completed = subprocess.run(
            [str(helper), "--request", str(request_path)],
            cwd=str(transient_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # FinalVerify1 ErrorFix1: WheelStyle neutral visibility is a derived-GLB
        # post-processing aid. A structural ordered-mapping validation failure is
        # fail-open and must never invalidate an otherwise valid converter GLB.
        if completed.returncode == 0 and output.is_file():
            try:
                wheel_visibility_summary = apply_neutral_wheel_visibility(
                    output, normalized_archive
                ).as_dict()
            except (OSError, ValueError, zipfile.BadZipFile, WheelVisibilityError) as exc:
                wheel_visibility_error = f"{type(exc).__name__}: {exc}"

            # FinalVerify1 A+B/C classification is metadata-only on the transient
            # derived GLB. Visibility is selected later in the viewer so A+B and C
            # can each be disabled without altering FH6 data or regenerating geometry.
            try:
                neutral_geometry_summary = annotate_neutral_geometry(
                    output, normalized_archive, carbin_entry
                ).as_dict()
            except (OSError, ValueError, zipfile.BadZipFile, NeutralGeometryError) as exc:
                neutral_geometry_error = f"{type(exc).__name__}: {exc}"
    except subprocess.TimeoutExpired as exc:
        raise ChassisConverterError("Vehicle conversion exceeded the 5-minute safety timeout.") from exc
    except OSError as exc:
        raise ChassisConverterError(f"Could not start Kfps.ChassisConverter.exe: {exc}") from exc
    finally:
        try:
            request_path.unlink(missing_ok=True)
        except OSError:
            pass
        # The derivative ZIP is only a converter transport. The GLB is the useful
        # reusable artifact, so never retain a second full copy of the vehicle ZIP.
        discard_near_lod_archive(normalized_archive)

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "Unknown converter failure").strip()
        raise ChassisConverterError(f"Chassis conversion failed:\n{details}")

    if not output.is_file():
        raise ChassisConverterError("Converter reported success but no GLB file was created.")
    if wheel_visibility_error:
        # ErrorFix1: preserve a valid GLB when WheelStyle ordered mapping cannot
        # be independently validated. Record the failure in memory only.
        wheel_visibility_summary = dict(wheel_visibility_summary or {})
        wheel_visibility_summary.setdefault("status", "validation_failed_proceeding")
    if neutral_geometry_error:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        raise ChassisConverterError(
            "Neutral A+B geometry classification failed closed; the derived GLB was discarded. "
            + neutral_geometry_error
        )
    try:
        header = output.read_bytes()[:12]
    except OSError as exc:
        raise ChassisConverterError(f"Generated GLB could not be reopened: {exc}") from exc
    if len(header) < 12 or header[:4] != b"glTF":
        output.unlink(missing_ok=True)
        raise ChassisConverterError("Generated file is not a valid GLB container (missing glTF magic).")

    stdout = completed.stdout.strip()
    diagnostics: dict = {}
    if stdout:
        # KFPS serializes the success object with WriteIndented=true, so the JSON spans
        # multiple lines. Parse the complete stdout first. If a future helper adds
        # informational text around it, fall back to the outermost JSON object.
        try:
            candidate = json.loads(stdout)
        except json.JSONDecodeError:
            candidate = None
            first = stdout.find("{")
            last = stdout.rfind("}")
            if first >= 0 and last > first:
                try:
                    candidate = json.loads(stdout[first:last + 1])
                except json.JSONDecodeError:
                    candidate = None
        if isinstance(candidate, dict):
            diagnostics = candidate

    # The raw carbin can mention optional/unselected models that are absent from
    # the archive. The pinned scene parser knows which instances are actually
    # active. Refuse only unresolved required active instances; skipped optional
    # instances remain diagnostic information rather than false failures.
    try:
        unresolved_required = int(diagnostics.get("unresolved_instance_count", 0) or 0)
    except (TypeError, ValueError):
        unresolved_required = 0
    if unresolved_required > 0:
        unresolved_paths = diagnostics.get("unresolved_paths") or []
        output.unlink(missing_ok=True)
        first = unresolved_paths[0] if isinstance(unresolved_paths, list) and unresolved_paths else "<unknown>"
        raise ChassisConverterError(
            f"Chassis scene has {unresolved_required} unresolved required model instance(s); "
            f"refusing a partial GLB. First unresolved path: {first}"
        )

    diagnostics.setdefault("car_id", asset.car_id)
    diagnostics.setdefault("model_code", asset.model_code)
    diagnostics.setdefault("archive", asset.archive_name)
    diagnostics.setdefault("carbin_entry", carbin_entry)
    normalization_data = asdict(normalization)
    diagnostics["near_lod_normalization_revision"] = normalization.revision
    diagnostics["near_lod_normalized_archive"] = normalization.normalized_archive
    diagnostics["near_lod_normalized_archive_retained"] = False
    diagnostics["near_lod_discovered_modelbin_references"] = normalization.discovered_modelbin_references
    diagnostics["near_lod_resolved_modelbin_references"] = normalization.resolved_modelbin_references
    diagnostics["near_lod_unresolved_modelbin_references"] = list(normalization.unresolved_modelbin_references)
    diagnostics["near_lod_referenced_modelbins"] = normalization.referenced_modelbins
    diagnostics["near_lod_parsed_modelbins"] = normalization.parsed_modelbins
    diagnostics["near_lod_normal_modelbins_patched"] = normalization.normal_modelbins_patched
    diagnostics["near_lod_mesh_lod_flags_patched"] = normalization.mesh_lod_flags_patched
    diagnostics["near_lod_old_selector_near_meshes"] = normalization.old_selector_near_meshes
    diagnostics["near_lod_normalized_near_meshes"] = normalization.normalized_near_meshes
    diagnostics["near_lod_recovered_lod0_specific_meshes"] = normalization.recovered_lod0_specific_meshes
    diagnostics["near_lod_slod_references"] = normalization.slod_references
    diagnostics["near_lod_slod_supplement_files"] = normalization.slod_supplement_files
    diagnostics["near_lod_slod_supplement_families"] = list(normalization.slod_supplement_families)
    diagnostics["near_lod_slod_carbin_paths_rewritten"] = normalization.slod_carbin_paths_rewritten
    diagnostics["near_lod_unparsed_referenced_modelbins"] = list(normalization.unparsed_referenced_modelbins)
    diagnostics["source_archive_path"] = normalization.source_archive
    diagnostics["source_archive_sha256"] = normalization.source_sha256
    diagnostics["source_archive_size"] = normalization.source_archive_size
    diagnostics["source_archive_mtime_ns"] = normalization.source_archive_mtime_ns
    diagnostics["near_lod_normalization"] = normalization_data
    diagnostics["glb_size"] = output.stat().st_size
    diagnostics["game_data_modified"] = False
    diagnostics["wheel_visibility_revision"] = WHEEL_VISIBILITY_REVISION
    diagnostics["wheel_visibility_status"] = (
        wheel_visibility_summary.get("status", "failed") if wheel_visibility_summary else "failed"
    )
    diagnostics["wheel_visibility"] = wheel_visibility_summary
    diagnostics["wheel_visibility_error"] = wheel_visibility_error
    diagnostics["neutral_geometry_revision"] = NEUTRAL_GEOMETRY_REVISION
    diagnostics["neutral_geometry_status"] = (
        neutral_geometry_summary.get("status", "failed") if neutral_geometry_summary else "failed"
    )
    diagnostics["neutral_geometry"] = neutral_geometry_summary
    diagnostics["neutral_geometry_error"] = neutral_geometry_error
    if progress:
        progress(f"Transient GLB created: {output}")
    return ConversionResult(str(output), str(helper), diagnostics)
