from __future__ import annotations

from .pipeline_diagnostics import timed, stage, record

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import hashlib
import json
import os
import struct
import subprocess
import tempfile
import zipfile
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator

from .native_texture_semantics import classify_native_texture_parameter

NATIVE_MATERIAL_TEXTURE_RESOLUTION_REVISION = 3
_BUNDLE_TAG = 0x47727562  # Grub bundle tag used by .swatchbin
_DDS_MAGIC = b"DDS "
_JSON_CHUNK_TYPE = 0x4E4F534A
_NATIVE_TEXTURE_DECODE_WORKERS = 12


def _native_texture_worker_limit() -> int:
    from ..app_options import load_options
    requested = load_options().render_workers
    if requested:
        return max(1, min(requested, os.cpu_count() or 1))
    # Leave scheduling headroom on small CPUs; extra SMT workers showed little
    # benefit above twelve in the measured 16-logical-processor workload.
    return min(_NATIVE_TEXTURE_DECODE_WORKERS, max(1, (os.cpu_count() or 4) * 3 // 4))


class NativeMaterialTextureError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeTextureBindingReference:
    mesh_name: str
    material_name: str
    parameter_hash: str
    path_hash: str
    texture_path: str
    parameter_name: str | None
    semantic: str
    semantic_resolution_mode: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NativeTexturePayload:
    texture_path: str
    normalized_path: str
    status: str
    resolution_mode: str
    source: str | None = None
    archive_entry: str | None = None
    payload_sha256: str | None = None
    payload_size: int | None = None
    cache_path: str | None = None
    detail: str | None = None
    decode_status: str = "not_requested"
    dds_path: str | None = None
    dds_sha256: str | None = None
    dds_size: int | None = None
    width: int | None = None
    height: int | None = None
    depth: int | None = None
    mip_levels: int | None = None
    dxgi_format: int | None = None
    dxgi_format_name: str | None = None
    decoder_detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NativeMaterialTextureReport:
    revision: int
    status: str
    decode_status: str
    reference_count: int
    unique_reference_count: int
    binding_count: int
    recognized_binding_count: int
    unknown_binding_count: int
    resolved_count: int
    unresolved_count: int
    located_unreadable_count: int
    decoded_count: int
    decode_failed_count: int
    decoder_unavailable_count: int
    manifest_path: str
    game_namespace_root: str | None
    textures: tuple[NativeTexturePayload, ...]
    bindings: tuple[NativeTextureBindingReference, ...]
    game_data_modified: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["textures"] = [item.as_dict() for item in self.textures]
        data["bindings"] = [item.as_dict() for item in self.bindings]
        return data


def _read_glb_json(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise NativeMaterialTextureError("GLB container is missing the glTF header.")
    version, declared_length = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise NativeMaterialTextureError(f"Unsupported GLB version: {version}")
    if declared_length != len(data):
        raise NativeMaterialTextureError(
            f"GLB length mismatch: header={declared_length}, actual={len(data)}"
        )

    cursor = 12
    while cursor + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, cursor)
        start = cursor + 8
        end = start + chunk_length
        if end > len(data):
            raise NativeMaterialTextureError("GLB chunk extends past the container.")
        if chunk_type == _JSON_CHUNK_TYPE:
            raw = data[start:end].rstrip(b" \t\r\n\0")
            try:
                document = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise NativeMaterialTextureError(f"GLB JSON chunk is invalid: {exc}") from exc
            if not isinstance(document, dict):
                raise NativeMaterialTextureError("GLB JSON root is not an object.")
            return document
        cursor = end
    raise NativeMaterialTextureError("GLB has no JSON chunk.")


def _mapping_value(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    folded = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        key = name.casefold()
        if key in folded:
            return folded[key]
    return None


def _iter_material_appearances(
    document: dict[str, Any],
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield KFPS appearance records from the real mesh-level layout plus legacy primitive fixtures."""
    meshes = document.get("meshes")
    if not isinstance(meshes, list):
        return

    for mesh in meshes:
        if not isinstance(mesh, dict):
            continue
        mesh_name = str(mesh.get("name") or "")
        mesh_extras = mesh.get("extras")
        yielded_mesh_appearance = False
        if isinstance(mesh_extras, dict):
            appearance = mesh_extras.get("kfps_material_appearance")
            if isinstance(appearance, dict):
                material_name = str(mesh_extras.get("kfps_material_name") or "")
                yielded_mesh_appearance = True
                yield mesh_name, material_name, appearance

        # Early tests/diagnostics wrote the appearance on primitive extras. Keep
        # compatibility, but do not double count when the authoritative mesh-level
        # appearance exists in a production KFPS GLB.
        if yielded_mesh_appearance:
            continue
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list):
            continue
        for primitive in primitives:
            if not isinstance(primitive, dict):
                continue
            extras = primitive.get("extras")
            if not isinstance(extras, dict):
                continue
            appearance = extras.get("kfps_material_appearance")
            if not isinstance(appearance, dict):
                continue
            material_name = str(extras.get("kfps_material_name") or "")
            yield mesh_name, material_name, appearance


def _clean_texture_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def collect_native_texture_bindings(
    glb_path: str | Path,
) -> tuple[NativeTextureBindingReference, ...]:
    """Preserve exact Texture2D parameter/path binding provenance per material mesh."""
    document = _read_glb_json(Path(glb_path))
    ordered: list[NativeTextureBindingReference] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for mesh_name, material_name, appearance in _iter_material_appearances(document):
        raw_bindings = _mapping_value(appearance, "textureBindings", "TextureBindings")
        if not isinstance(raw_bindings, list):
            continue
        for raw in raw_bindings:
            if not isinstance(raw, dict):
                continue
            texture_path = _clean_texture_path(
                _mapping_value(raw, "texturePath", "TexturePath")
            )
            if not texture_path:
                continue
            raw_parameter_hash = _mapping_value(raw, "parameterHash", "ParameterHash")
            raw_path_hash = _mapping_value(raw, "pathHash", "PathHash")
            semantic = classify_native_texture_parameter(raw_parameter_hash)
            parameter_hash = semantic.parameter_hash
            if not parameter_hash and raw_parameter_hash is not None:
                parameter_hash = str(raw_parameter_hash).strip().upper().removeprefix("0X")
            path_hash = str(raw_path_hash or "").strip().upper().removeprefix("0X")
            key = (
                mesh_name.casefold(),
                material_name.casefold(),
                parameter_hash.casefold(),
                path_hash.casefold(),
                texture_path.replace("\\", "/").casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            ordered.append(
                NativeTextureBindingReference(
                    mesh_name=mesh_name,
                    material_name=material_name,
                    parameter_hash=parameter_hash,
                    path_hash=path_hash,
                    texture_path=texture_path,
                    parameter_name=semantic.parameter_name,
                    semantic=semantic.semantic,
                    semantic_resolution_mode=semantic.resolution_mode,
                )
            )
    return tuple(ordered)


def collect_native_texture_paths(glb_path: str | Path) -> tuple[str, ...]:
    """Collect unique Texture2D paths from KFPS mesh-level appearance provenance."""
    document = _read_glb_json(Path(glb_path))
    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        path = _clean_texture_path(value)
        if not path:
            return
        key = path.replace("\\", "/").casefold()
        if key in seen:
            return
        seen.add(key)
        ordered.append(path)

    # TextureBindings retain the strongest provenance. Add them first.
    for _mesh_name, _material_name, appearance in _iter_material_appearances(document):
        raw_bindings = _mapping_value(appearance, "textureBindings", "TextureBindings")
        if isinstance(raw_bindings, list):
            for raw in raw_bindings:
                if isinstance(raw, dict):
                    add(_mapping_value(raw, "texturePath", "TexturePath"))

        # Keep old TexturePaths-only GLBs usable without inventing semantics.
        paths = _mapping_value(appearance, "texturePaths", "TexturePaths")
        if isinstance(paths, list):
            for value in paths:
                add(value)
    return tuple(ordered)


def _normalize_texture_path(texture_path: str) -> str:
    value = str(texture_path or "").strip().replace("\\", "/")
    lowered = value.casefold()
    if lowered.startswith("game:/"):
        value = value[6:]
    elif value.startswith("//"):
        return ""
    value = value.lstrip("/")
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return ""
    if ":" in parts[0]:
        return ""
    return "/".join(parts)


def _game_namespace_root(vehicle_archive: Path) -> tuple[Path | None, Path | None]:
    """Return the exact namespace root implied by an installed .../media/cars archive."""
    try:
        archive = vehicle_archive.expanduser().resolve()
    except OSError:
        return None, None
    cars = archive.parent
    media = cars.parent
    if cars.name.casefold() != "cars" or media.name.casefold() != "media":
        return None, None
    return media.parent, media


def _relative_candidates(normalized_path: str) -> tuple[str, ...]:
    if not normalized_path:
        return ()
    candidates: list[str] = []

    def add(value: str) -> None:
        normalized = value.replace("\\", "/").strip("/")
        if normalized and normalized.casefold() not in {item.casefold() for item in candidates}:
            candidates.append(normalized)

    add(normalized_path)
    if not normalized_path.casefold().startswith("media/"):
        add(f"media/{normalized_path}")
    return tuple(candidates)


def _safe_loose_path(namespace_root: Path, relative_path: str) -> Path | None:
    candidate = namespace_root.joinpath(*relative_path.split("/"))
    try:
        resolved_root = namespace_root.resolve()
        resolved = candidate.resolve()
        if not resolved.is_relative_to(resolved_root):
            return None
    except AttributeError:
        root_text = os.path.normcase(str(namespace_root.resolve())).rstrip("\\/") + os.sep
        resolved = candidate.resolve()
        if not os.path.normcase(str(resolved)).startswith(root_text):
            return None
    except OSError:
        return None
    return resolved


def _valid_swatch_payload(payload: bytes) -> bool:
    return len(payload) >= 4 and struct.unpack_from("<I", payload, 0)[0] == _BUNDLE_TAG


def _valid_dds_payload(payload: bytes) -> bool:
    return len(payload) >= 148 and payload[:4] == _DDS_MAGIC


def _read_zip_entry(
    zip_path: Path,
    *,
    exact_entry: str | None = None,
    basename: str | None = None,
) -> tuple[str, bytes | None, str | None] | None:
    """Return (entry name, bytes or None, read error or None)."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            matches = []
            if exact_entry is not None:
                target = exact_entry.replace("\\", "/").strip("/").casefold()
                matches = [
                    info for info in files
                    if info.filename.replace("\\", "/").strip("/").casefold() == target
                ]
            elif basename is not None:
                target = basename.casefold()
                matches = [
                    info for info in files
                    if Path(info.filename.replace("\\", "/")).name.casefold() == target
                ]
            if len(matches) != 1:
                return None
            info = matches[0]
            try:
                return info.filename, archive.read(info), None
            except (NotImplementedError, RuntimeError, OSError, zipfile.BadZipFile) as exc:
                return info.filename, None, f"{type(exc).__name__}: {exc}"
    except (OSError, zipfile.BadZipFile):
        return None


def _vehicle_archive_candidates(normalized_path: str, vehicle_archive: Path) -> tuple[str, ...]:
    """Build only structurally justified entry candidates for the selected car ZIP."""
    candidates: list[str] = []
    parts = normalized_path.split("/")
    model = vehicle_archive.stem.casefold()

    for index, part in enumerate(parts):
        if part.casefold() == model and index + 1 < len(parts):
            candidates.append("/".join(parts[index + 1 :]))
            break
    for index, part in enumerate(parts):
        if part.casefold() == "scene" and index + 1 < len(parts):
            candidate = "/".join(parts[index:])
            if candidate.casefold() not in {item.casefold() for item in candidates}:
                candidates.append(candidate)
            break
    return tuple(candidates)


def _try_vehicle_archive(
    normalized_path: str, vehicle_archive: Path
) -> tuple[str, str, bytes | None, str | None] | None:
    for entry in _vehicle_archive_candidates(normalized_path, vehicle_archive):
        result = _read_zip_entry(vehicle_archive, exact_entry=entry)
        if result is not None:
            entry_name, payload, error = result
            return str(vehicle_archive), entry_name, payload, error
    return None


def _try_loose_file(
    namespace_root: Path, relative_paths: Iterable[str]
) -> tuple[str, bytes | None, str | None] | None:
    for relative in relative_paths:
        path = _safe_loose_path(namespace_root, relative)
        if path is None or not path.is_file():
            continue
        try:
            return str(path), path.read_bytes(), None
        except OSError as exc:
            return str(path), None, f"{type(exc).__name__}: {exc}"
    return None


def _try_derived_zip(
    namespace_root: Path, relative_paths: Iterable[str]
) -> tuple[str, str, bytes | None, str | None] | None:
    unreadable: tuple[str, str, bytes | None, str | None] | None = None
    for relative in relative_paths:
        parts = [part for part in relative.split("/") if part]
        for prefix_length in range(len(parts) - 1, 0, -1):
            zip_path = Path(str(namespace_root.joinpath(*parts[:prefix_length])) + ".zip")
            if not zip_path.is_file():
                continue
            entry = "/".join(parts[prefix_length:])
            result = _read_zip_entry(zip_path, exact_entry=entry)
            if result is None:
                continue
            entry_name, payload, error = result
            candidate = (str(zip_path), entry_name, payload, error)
            if payload is not None:
                return candidate
            if unreadable is None:
                unreadable = candidate
    return unreadable


@lru_cache(maxsize=8)
def _priority_texture_zips(media_root_text: str) -> tuple[str, ...]:
    media_root = Path(media_root_text)
    if not media_root.is_dir():
        return ()
    matches: list[str] = []
    try:
        for root, _dirs, files in os.walk(media_root):
            for filename in files:
                if filename.casefold() == "textures.zip":
                    matches.append(str(Path(root) / filename))
    except OSError:
        return tuple(sorted(set(matches), key=str.casefold))
    return tuple(sorted(set(matches), key=str.casefold))


def _try_unique_priority_filename(
    media_root: Path, basename: str
) -> tuple[str, str, bytes | None, str | None] | str | None:
    matches: list[tuple[str, str, bytes | None, str | None]] = []
    for zip_text in _priority_texture_zips(str(media_root.resolve())):
        zip_path = Path(zip_text)
        result = _read_zip_entry(zip_path, basename=basename)
        if result is None:
            continue
        entry_name, payload, error = result
        matches.append((str(zip_path), entry_name, payload, error))
        if len(matches) > 1:
            return "ambiguous"
    return matches[0] if matches else None


def _cache_payload(
    payload: bytes,
    cache_root: Path,
    *,
    suffix: str = ".swatchbin",
) -> tuple[str, int, str]:
    digest = hashlib.sha256(payload).hexdigest()
    directory = cache_root / "native_material_textures"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}{suffix}"
    if target.is_file():
        try:
            if target.read_bytes() == payload:
                return digest, len(payload), str(target)
        except OSError:
            pass

    fd, name = tempfile.mkstemp(prefix=f".{digest}.", suffix=".tmp", dir=directory)
    os.close(fd)
    temporary = Path(name)
    try:
        temporary.write_bytes(payload)
        temporary.replace(target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return digest, len(payload), str(target)


def _resolved_payload(
    texture_path: str,
    normalized_path: str,
    resolution_mode: str,
    source: str,
    archive_entry: str | None,
    payload: bytes,
    cache_root: Path,
) -> NativeTexturePayload:
    if not _valid_swatch_payload(payload):
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized_path,
            status="payload_not_swatchbin",
            resolution_mode=resolution_mode,
            source=source,
            archive_entry=archive_entry,
            payload_size=len(payload),
            detail="Resolved bytes do not begin with the expected Grub bundle tag.",
        )
    digest, size, cached = _cache_payload(payload, cache_root)
    return NativeTexturePayload(
        texture_path=texture_path,
        normalized_path=normalized_path,
        status="resolved_payload",
        resolution_mode=resolution_mode,
        source=source,
        archive_entry=archive_entry,
        payload_sha256=digest,
        payload_size=size,
        cache_path=cached,
    )


def resolve_native_texture_reference(
    texture_path: str,
    vehicle_archive: str | Path,
    cache_root: str | Path,
) -> NativeTexturePayload:
    vehicle_archive = Path(vehicle_archive).expanduser().resolve()
    cache_root = Path(cache_root).expanduser().resolve()
    normalized = _normalize_texture_path(texture_path)
    if not normalized:
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path="",
            status="unsupported_texture_reference",
            resolution_mode="unresolved",
            detail="Texture path is empty, absolute, non-Game, or contains parent traversal.",
        )
    if Path(normalized).suffix.casefold() != ".swatchbin":
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized,
            status="unsupported_texture_reference",
            resolution_mode="unresolved",
            detail="Only native .swatchbin Texture2D payloads are resolved in this revision.",
        )

    local = _try_vehicle_archive(normalized, vehicle_archive)
    if local is not None:
        source, entry, payload, error = local
        if payload is not None:
            return _resolved_payload(
                texture_path, normalized, "vehicle_archive_exact", source, entry, payload, cache_root
            )
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized,
            status="payload_located_unreadable",
            resolution_mode="vehicle_archive_exact",
            source=source,
            archive_entry=entry,
            detail=error,
        )

    namespace_root, media_root = _game_namespace_root(vehicle_archive)
    if namespace_root is None or media_root is None:
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized,
            status="game_namespace_unavailable",
            resolution_mode="unresolved",
            detail="Vehicle archive is not under a validated .../media/cars install layout.",
        )

    relatives = _relative_candidates(normalized)

    loose = _try_loose_file(namespace_root, relatives)
    if loose is not None:
        source, payload, error = loose
        if payload is not None:
            return _resolved_payload(
                texture_path, normalized, "game_loose_exact", source, None, payload, cache_root
            )
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized,
            status="payload_located_unreadable",
            resolution_mode="game_loose_exact",
            source=source,
            detail=error,
        )

    derived = _try_derived_zip(namespace_root, relatives)
    if derived is not None:
        source, entry, payload, error = derived
        if payload is not None:
            return _resolved_payload(
                texture_path, normalized, "derived_zip_exact", source, entry, payload, cache_root
            )
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized,
            status="payload_located_unreadable",
            resolution_mode="derived_zip_exact",
            source=source,
            archive_entry=entry,
            detail=error,
        )

    basename = Path(normalized).name
    fallback = _try_unique_priority_filename(media_root, basename)
    if fallback == "ambiguous":
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized,
            status="ambiguous_priority_archive_filename",
            resolution_mode="unresolved",
            detail="More than one textures.zip entry shares the referenced filename; no guess was made.",
        )
    if isinstance(fallback, tuple):
        source, entry, payload, error = fallback
        if payload is not None:
            return _resolved_payload(
                texture_path,
                normalized,
                "textures_zip_unique_filename",
                source,
                entry,
                payload,
                cache_root,
            )
        return NativeTexturePayload(
            texture_path=texture_path,
            normalized_path=normalized,
            status="payload_located_unreadable",
            resolution_mode="textures_zip_unique_filename",
            source=source,
            archive_entry=entry,
            detail=error,
        )

    return NativeTexturePayload(
        texture_path=texture_path,
        normalized_path=normalized,
        status="reference_unresolved",
        resolution_mode="unresolved",
        detail="No exact loose/derived-archive asset or unique textures.zip filename was resolved.",
    )


def _decoder_value(diagnostic: dict[str, Any], *names: str) -> Any:
    return _mapping_value(diagnostic, *names)


def _parse_decoder_diagnostic(stdout: str) -> dict[str, Any] | None:
    text = str(stdout or "").strip()
    if not text:
        return None
    try:
        candidate = json.loads(text)
    except json.JSONDecodeError:
        candidate = None
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            try:
                candidate = json.loads(text[first : last + 1])
            except json.JSONDecodeError:
                candidate = None
    return candidate if isinstance(candidate, dict) else None


def _decode_resolved_payload(
    item: NativeTexturePayload,
    decoder_helper: Path | None,
    cache_root: Path,
) -> NativeTexturePayload:
    if item.status != "resolved_payload" or not item.cache_path or not item.payload_sha256:
        return item
    if decoder_helper is None:
        return replace(item, decode_status="decoder_unavailable")
    try:
        helper = decoder_helper.expanduser().resolve()
    except OSError as exc:
        return replace(
            item,
            decode_status="decoder_unavailable",
            decoder_detail=f"Decoder path could not be resolved: {exc}",
        )
    if not helper.is_file():
        return replace(
            item,
            decode_status="decoder_unavailable",
            decoder_detail=f"Verified decoder helper does not exist: {helper}",
        )

    swatch = Path(item.cache_path).expanduser().resolve()
    directory = cache_root / "native_material_textures"
    directory.mkdir(parents=True, exist_ok=True)
    dds = directory / f"{item.payload_sha256}.dds"

    if dds.is_file():
        try:
            cached = dds.read_bytes()
        except OSError:
            cached = b""
        if _valid_dds_payload(cached):
            return replace(
                item,
                decode_status="decoded_dds_cached",
                dds_path=str(dds),
                dds_sha256=hashlib.sha256(cached).hexdigest(),
                dds_size=len(cached),
            )
        try:
            dds.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        with stage("native_texture_decoder_subprocess"):
            completed = subprocess.run(
                [str(helper), "--decode-swatchbin", str(swatch), str(dds)],
                cwd=str(directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except subprocess.TimeoutExpired:
        return replace(
            item,
            decode_status="decode_failed",
            decoder_detail="Native swatchbin decode exceeded the 120-second timeout.",
        )
    except OSError as exc:
        return replace(
            item,
            decode_status="decode_failed",
            decoder_detail=f"Could not start verified native texture decoder: {exc}",
        )

    if completed.returncode != 0:
        try:
            dds.unlink(missing_ok=True)
        except OSError:
            pass
        details = (completed.stderr or completed.stdout or "Unknown decoder failure").strip()
        return replace(
            item,
            decode_status="decode_failed",
            decoder_detail=details[:2000],
        )

    diagnostic = _parse_decoder_diagnostic(completed.stdout)
    if not dds.is_file():
        return replace(
            item,
            decode_status="decode_failed",
            decoder_detail="Native decoder reported success but no DDS derivative was created.",
        )
    try:
        dds_bytes = dds.read_bytes()
    except OSError as exc:
        return replace(
            item,
            decode_status="decode_failed",
            decoder_detail=f"Decoded DDS derivative could not be reopened: {exc}",
        )
    if not _valid_dds_payload(dds_bytes):
        try:
            dds.unlink(missing_ok=True)
        except OSError:
            pass
        return replace(
            item,
            decode_status="decode_failed",
            decoder_detail="Native decoder output is not a valid DDS DX10 container.",
        )

    actual_sha = hashlib.sha256(dds_bytes).hexdigest()
    if diagnostic is not None:
        reported_sha = _decoder_value(diagnostic, "ddsSha256", "DdsSha256")
        if isinstance(reported_sha, str) and reported_sha and reported_sha.casefold() != actual_sha.casefold():
            try:
                dds.unlink(missing_ok=True)
            except OSError:
                pass
            return replace(
                item,
                decode_status="decode_failed",
                decoder_detail=(
                    "Decoder DDS SHA-256 diagnostic does not match the derivative bytes: "
                    f"reported={reported_sha}, actual={actual_sha}."
                ),
            )

    def integer_value(*names: str) -> int | None:
        if diagnostic is None:
            return None
        value = _decoder_value(diagnostic, *names)
        if isinstance(value, bool):
            return None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    format_name = None
    if diagnostic is not None:
        value = _decoder_value(diagnostic, "dxgiFormatName", "DxgiFormatName")
        if isinstance(value, str) and value:
            format_name = value

    return replace(
        item,
        decode_status="decoded_dds",
        dds_path=str(dds),
        dds_sha256=actual_sha,
        dds_size=len(dds_bytes),
        width=integer_value("width", "Width"),
        height=integer_value("height", "Height"),
        depth=integer_value("depth", "Depth"),
        mip_levels=integer_value("mipLevels", "MipLevels"),
        dxgi_format=integer_value("dxgiFormat", "DxgiFormat"),
        dxgi_format_name=format_name,
    )


def _decode_resolved_payloads(
    items: tuple[NativeTexturePayload, ...],
    decoder_helper: Path | None,
    cache_root: Path,
) -> tuple[NativeTexturePayload, ...]:
    # Only independent native helper processes overlap. Archive resolution and
    # the livery renderer stay on the caller thread. Equal payload hashes share
    # a DDS destination, so keep those items sequential within one group.
    groups: dict[object, list[tuple[int, NativeTexturePayload]]] = {}
    for index, item in enumerate(items):
        key = item.payload_sha256 if item.payload_sha256 else index
        groups.setdefault(key, []).append((index, item))
    workers = min(_native_texture_worker_limit(), len(groups))
    if decoder_helper is None or workers <= 1:
        return tuple(_decode_resolved_payload(item, decoder_helper, cache_root) for item in items)

    def decode_group(group):
        return [(index, _decode_resolved_payload(item, decoder_helper, cache_root))
                for index, item in group]

    record('native_texture_decode_schedule', workers=workers, payload_groups=len(groups))
    results = list(items)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='fh6-native-dds') as pool:
        # Preserve the caller's per-preview trace without sharing an entered Context.
        futures = [pool.submit(copy_context().run, decode_group, group) for group in groups.values()]
        for future in futures:
            for index, item in future.result():
                results[index] = item
    return tuple(results)


def _automatic_decoder_helper() -> tuple[Path | None, str | None]:
    """Resolve only the SHA-verified bundled helper; never fall back to an arbitrary executable."""
    try:
        from .wheel_morph_helper import WheelMorphHelperError, verified_bundled_wheel_morph_helper

        return verified_bundled_wheel_morph_helper(), None
    except WheelMorphHelperError as exc:
        return None, f"Bundled native texture decoder failed integrity verification: {exc}"


@timed('native_texture_prepare')
def resolve_native_material_textures(
    glb_path: str | Path,
    vehicle_archive: str | Path,
    *,
    cache_root: str | Path | None = None,
    decoder_helper: str | Path | None = None,
    decode_native: bool = True,
) -> NativeMaterialTextureReport:
    glb = Path(glb_path).expanduser().resolve()
    source_archive = Path(vehicle_archive).expanduser().resolve()
    target_root = (
        Path(cache_root).expanduser().resolve()
        if cache_root is not None
        else glb.parent
    )
    target_root.mkdir(parents=True, exist_ok=True)

    texture_paths = collect_native_texture_paths(glb)
    bindings = collect_native_texture_bindings(glb)
    resolved_items = tuple(
        resolve_native_texture_reference(path, source_archive, target_root)
        for path in texture_paths
    )

    decoder_detail = None
    if not decode_native:
        results = resolved_items
    else:
        if decoder_helper is not None:
            decoder_path = Path(decoder_helper)
        else:
            decoder_path, decoder_detail = _automatic_decoder_helper()
        results = _decode_resolved_payloads(resolved_items, decoder_path, target_root)
        if decoder_detail:
            results = tuple(
                replace(item, decoder_detail=decoder_detail)
                if item.decode_status == "decoder_unavailable" and not item.decoder_detail
                else item
                for item in results
            )

    resolved = sum(item.status == "resolved_payload" for item in results)
    unreadable = sum(item.status == "payload_located_unreadable" for item in results)
    unresolved = len(results) - resolved
    decoded = sum(item.decode_status in {"decoded_dds", "decoded_dds_cached"} for item in results)
    decode_failed = sum(item.decode_status == "decode_failed" for item in results)
    decoder_unavailable = sum(item.decode_status == "decoder_unavailable" for item in results)
    recognized_bindings = sum(item.semantic != "unknown" for item in bindings)
    unknown_bindings = len(bindings) - recognized_bindings

    if not results:
        status = "no_texture_references"
    elif resolved == len(results):
        status = "resolved_all"
    elif resolved:
        status = "resolved_partial"
    else:
        status = "unresolved"

    if not decode_native:
        decode_status = "not_requested"
    elif resolved == 0:
        decode_status = "no_resolved_payloads"
    elif decoded == resolved:
        decode_status = "decoded_all"
    elif decoded:
        decode_status = "decoded_partial"
    elif decoder_unavailable == resolved:
        decode_status = "decoder_unavailable"
    else:
        decode_status = "decode_failed"

    namespace_root, _media_root = _game_namespace_root(source_archive)
    manifest = glb.with_suffix(glb.suffix + ".native_textures.json")
    report = NativeMaterialTextureReport(
        revision=NATIVE_MATERIAL_TEXTURE_RESOLUTION_REVISION,
        status=status,
        decode_status=decode_status,
        reference_count=len(texture_paths),
        unique_reference_count=len(texture_paths),
        binding_count=len(bindings),
        recognized_binding_count=recognized_bindings,
        unknown_binding_count=unknown_bindings,
        resolved_count=resolved,
        unresolved_count=unresolved,
        located_unreadable_count=unreadable,
        decoded_count=decoded,
        decode_failed_count=decode_failed,
        decoder_unavailable_count=decoder_unavailable,
        manifest_path=str(manifest),
        game_namespace_root=str(namespace_root) if namespace_root is not None else None,
        textures=results,
        bindings=bindings,
        game_data_modified=False,
    )
    payload = report.as_dict()
    payload["format"] = "fh6_native_material_texture_resolution_v3"
    temp = manifest.with_suffix(manifest.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(manifest)
    return report
