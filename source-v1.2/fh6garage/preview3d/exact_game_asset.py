from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any

from .native_material_textures import (
    _game_namespace_root,
    _normalize_texture_path,
    _relative_candidates,
    _try_derived_zip,
    _try_loose_file,
    _try_vehicle_archive,
)


EXACT_GAME_ASSET_REVISION = 1


@dataclass(frozen=True)
class ExactGameAssetPayload:
    reference_path: str
    normalized_path: str
    status: str
    resolution_mode: str
    source: str | None = None
    archive_entry: str | None = None
    payload_sha256: str | None = None
    payload_size: int | None = None
    cache_path: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cache_payload(
    reference_path: str,
    normalized_path: str,
    resolution_mode: str,
    source: str,
    archive_entry: str | None,
    payload: bytes,
    cache_root: Path,
) -> ExactGameAssetPayload:
    digest = hashlib.sha256(payload).hexdigest()
    suffix = Path(normalized_path).suffix.lower()
    if not suffix or len(suffix) > 24:
        suffix = ".bin"
    target = cache_root / "exact-game-assets" / digest[:2] / f"{digest}{suffix}"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.stat().st_size != len(payload):
            target.write_bytes(payload)
        cached = str(target.resolve())
    except OSError as exc:
        return ExactGameAssetPayload(
            reference_path=reference_path,
            normalized_path=normalized_path,
            status="payload_cache_failed",
            resolution_mode=resolution_mode,
            source=source,
            archive_entry=archive_entry,
            payload_sha256=digest,
            payload_size=len(payload),
            detail=f"{type(exc).__name__}: {exc}",
        )
    return ExactGameAssetPayload(
        reference_path=reference_path,
        normalized_path=normalized_path,
        status="resolved_payload",
        resolution_mode=resolution_mode,
        source=source,
        archive_entry=archive_entry,
        payload_sha256=digest,
        payload_size=len(payload),
        cache_path=cached,
    )


def resolve_exact_game_asset_reference(
    reference_path: str,
    vehicle_archive: str | Path,
    cache_root: str | Path,
) -> ExactGameAssetPayload:
    """Resolve arbitrary FH6 asset bytes through structurally exact path modes only.

    This shares the already-validated path normalization and exact vehicle/loose/
    derived-zip lookup rules with the native Texture2D resolver, but intentionally
    performs no swatchbin/DDS magic validation and exposes no filename fallback.
    It is therefore suitable for intermediate .materialbin traversal without
    weakening the native texture resolver's payload contract.
    """
    raw_path = str(reference_path or "").strip()
    normalized = _normalize_texture_path(raw_path)
    if not normalized:
        return ExactGameAssetPayload(
            reference_path=raw_path,
            normalized_path="",
            status="reference_invalid",
            resolution_mode="none",
            detail="The reference path is empty, absolute/unsafe, or contains parent traversal.",
        )

    vehicle = Path(vehicle_archive).expanduser().resolve()
    cache = Path(cache_root).expanduser().resolve()

    local = _try_vehicle_archive(normalized, vehicle)
    if local is not None:
        source, entry, payload, error = local
        if payload is not None:
            return _cache_payload(
                raw_path, normalized, "vehicle_archive_exact", source, entry, payload, cache
            )
        return ExactGameAssetPayload(
            reference_path=raw_path,
            normalized_path=normalized,
            status="payload_located_unreadable",
            resolution_mode="vehicle_archive_exact",
            source=source,
            archive_entry=entry,
            detail=error,
        )

    namespace_root, _media = _game_namespace_root(vehicle)
    if namespace_root is None:
        return ExactGameAssetPayload(
            reference_path=raw_path,
            normalized_path=normalized,
            status="reference_unresolved",
            resolution_mode="none",
            detail="The selected vehicle archive does not establish an installed .../media/cars namespace.",
        )

    relatives = _relative_candidates(normalized)
    loose = _try_loose_file(namespace_root, relatives)
    if loose is not None:
        source, payload, error = loose
        if payload is not None:
            return _cache_payload(
                raw_path, normalized, "game_loose_exact", source, None, payload, cache
            )
        return ExactGameAssetPayload(
            reference_path=raw_path,
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
            return _cache_payload(
                raw_path, normalized, "derived_zip_exact", source, entry, payload, cache
            )
        return ExactGameAssetPayload(
            reference_path=raw_path,
            normalized_path=normalized,
            status="payload_located_unreadable",
            resolution_mode="derived_zip_exact",
            source=source,
            archive_entry=entry,
            detail=error,
        )

    return ExactGameAssetPayload(
        reference_path=raw_path,
        normalized_path=normalized,
        status="reference_unresolved",
        resolution_mode="none",
        detail="No structurally exact vehicle-archive, loose-game, or derived-zip match was found.",
    )
