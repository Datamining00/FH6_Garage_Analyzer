from __future__ import annotations

import importlib
import io
import os
import re
import sys
import threading
import zipfile
from functools import lru_cache
from pathlib import Path


KFPS_VENDOR_COMMIT = "8965780b8966e09d2f2a17e4d0684cdd44d7437c"


class ExactLiveryPreviewError(RuntimeError):
    """Raised when an exact local FH6 vehicle projection cannot be produced."""


_LOCK = threading.RLock()
_DECAL_MEMBER_RE = re.compile(r"(?:^|/)decal[_-]?0*(\d+)\.swatchbin$", re.IGNORECASE)


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FH6GarageAnalyzer"
    return Path.home() / ".fh6garage"


def _saved_game_folder_path() -> Path:
    return _app_data_dir() / "fh6_game_folder.txt"


def _vehicle_index_cache_path() -> Path:
    return _app_data_dir() / "fh6_vehicle_assets.json"


def _vendor_candidates() -> tuple[Path, ...]:
    candidates = [_source_root() / "vendor" / "kfps"]
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "vendor" / "kfps")
    return tuple(candidates)


def _prepare_vendor_import_path() -> None:
    for candidate in _vendor_candidates():
        if candidate.is_dir():
            text = str(candidate)
            if text not in sys.path:
                sys.path.insert(0, text)
            return


def _load_backend():
    _prepare_vendor_import_path()
    try:
        vehicle_assets = importlib.import_module("tools.livery.vehicle_assets")
        render_contract = importlib.import_module("tools.livery.render_contract")
        raster_decals = importlib.import_module("tools.livery.raster_decals")
    except Exception as exc:
        raise ExactLiveryPreviewError(
            "차량별 FH6 projection 구성요소를 불러오지 못했습니다. v1.4 빌드를 복구해 주세요."
        ) from exc
    return vehicle_assets, render_contract, raster_decals


@lru_cache(maxsize=8)
def _normalize_game_folder_cached(path_text: str) -> Path:
    vehicle_assets, _render_contract, _raster_decals = _load_backend()
    try:
        return Path(vehicle_assets.normalize_fh6_game_folder(path_text)).resolve()
    except Exception as exc:
        raise ExactLiveryPreviewError(
            "선택한 폴더에서 FH6 차량 아카이브를 찾지 못했습니다. "
            "Forza Horizon 6 폴더 또는 Content 폴더를 선택해 주세요."
        ) from exc


def _normalize_game_folder(path: Path | str) -> Path:
    return _normalize_game_folder_cached(str(Path(path).expanduser()))


def set_fh6_game_folder(path: Path | str) -> Path:
    normalized = _normalize_game_folder(path)
    preference = _saved_game_folder_path()
    preference.parent.mkdir(parents=True, exist_ok=True)
    temporary = preference.with_suffix(".tmp")
    temporary.write_text(str(normalized), encoding="utf-8")
    os.replace(temporary, preference)
    clear_exact_preview_cache()
    return normalized


def _saved_game_folder_text() -> str:
    preference = _saved_game_folder_path()
    try:
        return preference.read_text(encoding="utf-8").strip() if preference.is_file() else ""
    except OSError:
        return ""


def _quick_existing_path(value: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        candidate = Path(text).expanduser()
        return candidate if candidate.exists() else None
    except OSError:
        return None


def saved_fh6_game_folder() -> Path | None:
    """Return the saved path without scanning FH6 archives."""
    return _quick_existing_path(_saved_game_folder_text())


def configured_fh6_game_folder() -> Path | None:
    """Return an explicitly configured path without automatic discovery."""
    for value in (os.environ.get("FH6_GAME_FOLDER", ""), _saved_game_folder_text()):
        candidate = _quick_existing_path(value)
        if candidate is not None:
            return candidate
    return None


@lru_cache(maxsize=1)
def _discover_fh6_game_folder_cached() -> Path | None:
    vehicle_assets, _render_contract, _raster_decals = _load_backend()
    try:
        discovered = vehicle_assets.discover_fh6_game_folder()
    except Exception:
        discovered = None
    if not discovered:
        return None
    try:
        return _normalize_game_folder(discovered)
    except ExactLiveryPreviewError:
        return None


def require_fh6_game_folder() -> Path:
    configured = configured_fh6_game_folder()
    if configured is not None:
        try:
            return _normalize_game_folder(configured)
        except ExactLiveryPreviewError:
            pass

    discovered = _discover_fh6_game_folder_cached()
    if discovered is not None:
        return discovered

    raise ExactLiveryPreviewError(
        "원본과 일치하는 리버리 미리보기에는 로컬 FH6 설치 파일의 차량 projection mask가 필요합니다. "
        "이미지 창에서 'FH6 설치 폴더 지정'을 눌러 게임 폴더 또는 Content 폴더를 선택해 주세요."
    )


@lru_cache(maxsize=4)
def _vehicle_index(game_folder_text: str):
    vehicle_assets, _render_contract, _raster_decals = _load_backend()
    cache = _vehicle_index_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        return vehicle_assets.load_or_build_vehicle_asset_index(game_folder_text, cache)
    except Exception as exc:
        raise ExactLiveryPreviewError(f"FH6 차량 아카이브 색인을 만들지 못했습니다: {exc}") from exc


def resolve_vehicle_asset(car_id: int, game_folder: Path | str | None = None):
    game = Path(game_folder).resolve() if game_folder is not None else require_fh6_game_folder()
    asset = _vehicle_index(str(game)).get(int(car_id))
    if asset is None:
        raise ExactLiveryPreviewError(
            f"Car ID {int(car_id)}에 대응하는 로컬 FH6 차량 아카이브를 찾지 못했습니다."
        )
    return asset


@lru_cache(maxsize=24)
def _vehicle_masks_cached(
    game_folder_text: str,
    car_id: int,
    archive_size: int,
    archive_mtime_ns: int,
):
    del archive_size, archive_mtime_ns
    asset = resolve_vehicle_asset(int(car_id), Path(game_folder_text))
    _vehicle_assets, render_contract, _raster_decals = _load_backend()
    try:
        return render_contract._archive_masks(asset)
    except Exception as exc:
        raise ExactLiveryPreviewError(
            f"Car ID {int(car_id)}의 FH6 projection mask 세트를 읽지 못했습니다: {exc}"
        ) from exc


def _vehicle_masks(car_id: int, game_folder: Path | str):
    game = Path(game_folder).resolve()
    asset = resolve_vehicle_asset(int(car_id), game)
    return _vehicle_masks_cached(
        str(game),
        int(car_id),
        int(getattr(asset, "archive_size", 0)),
        int(getattr(asset, "archive_mtime_ns", 0)),
    )


def _index_decal_members(names) -> dict[int, str]:
    """Index Decals.zip members by numeric decal ID without assuming case/padding."""
    indexed: dict[int, str] = {}
    for raw_name in names:
        name = str(raw_name).replace("\\", "/")
        match = _DECAL_MEMBER_RE.search(name)
        if match is None:
            continue
        try:
            raster_id = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if raster_id > 0:
            indexed.setdefault(raster_id, str(raw_name))
    return indexed


class IndexedFH6RasterDecalResolver:
    """Fail-closed FH6 raster resolver with archive-member indexing and diagnostics."""

    def __init__(self, game_folder: Path | str):
        _vehicle_assets, _render_contract, raster_decals = _load_backend()
        self._backend = raster_decals
        try:
            self.archive = Path(raster_decals.resolve_fh6_decals_archive(game_folder)).resolve()
            with zipfile.ZipFile(self.archive) as bundle:
                self._members = _index_decal_members(bundle.namelist())
        except Exception as exc:
            raise ExactLiveryPreviewError(
                "FH6 내장 래스터 데칼 아카이브를 찾거나 색인하지 못했습니다."
            ) from exc
        self._cache: dict[int, object | None] = {}
        self._errors: dict[int, str] = {}

    def __call__(self, raster_id: int):
        raster_id = int(raster_id)
        if raster_id in self._cache:
            return self._cache[raster_id]
        member = self._members.get(raster_id)
        if member is None:
            self._errors[raster_id] = "archive member not found"
            self._cache[raster_id] = None
            return None
        try:
            with zipfile.ZipFile(self.archive) as bundle:
                data = bundle.read(member)
            image = self._backend.decode_fh6_decal_swatch(data)
        except Exception as exc:
            self._errors[raster_id] = f"{member}: {exc}"
            image = None
        self._cache[raster_id] = image
        return image

    def missing_description(self, raster_id: int) -> str:
        raster_id = int(raster_id)
        member = self._members.get(raster_id)
        if member is not None:
            detail = self._errors.get(raster_id, "decode failed")
            return f"Decals.zip 멤버 {member!r}는 존재하지만 해석하지 못했습니다: {detail}"
        available = sorted(self._members)
        nearest = sorted(available, key=lambda value: (abs(value - raster_id), value))[:6]
        nearest_text = ", ".join(str(value) for value in nearest) if nearest else "없음"
        return (
            f"Decals.zip에서 raster ID {raster_id}에 대응하는 swatchbin을 찾지 못했습니다. "
            f"색인된 데칼 {len(available):,}개 · 인접 ID: {nearest_text}"
        )


@lru_cache(maxsize=4)
def _raster_resolver_cached(game_folder_text: str):
    return IndexedFH6RasterDecalResolver(game_folder_text)


def raster_resolver_for_game(game_folder: Path | str | None = None):
    game = Path(game_folder).resolve() if game_folder is not None else require_fh6_game_folder()
    return _raster_resolver_cached(str(game))


def _projection_record(section: str, car_id: int, game: Path):
    _vehicle_assets, render_contract, _raster_decals = _load_backend()
    slot = getattr(render_contract, "SECTION_TO_SLOT", {}).get(str(section))
    if not slot:
        raise ExactLiveryPreviewError(f"지원하지 않는 FH6 livery section입니다: {section}")
    mask_record = _vehicle_masks(int(car_id), game).get(slot)
    if mask_record is None:
        raise ExactLiveryPreviewError(
            f"이 차량은 {section} 영역의 정확한 FH6 projection mask를 제공하지 않습니다."
        )
    mask, projection, mask_hash = mask_record
    if mask.getbbox() is None:
        raise ExactLiveryPreviewError(
            f"이 차량의 {section} projection mask가 비어 있어 정확한 미리보기를 만들 수 없습니다."
        )
    return render_contract, slot, mask, projection, mask_hash


def apply_exact_vehicle_projection(
    png_bytes: bytes,
    section: str,
    car_id: int,
    *,
    game_folder: Path | str | None = None,
) -> bytes:
    """Apply the exact 2048x1024 car-specific FH6 projection mask."""
    return apply_exact_vehicle_projection_scaled(
        png_bytes,
        section,
        car_id,
        scale=1,
        game_folder=game_folder,
    )


def apply_exact_vehicle_projection_scaled(
    png_bytes: bytes,
    section: str,
    car_id: int,
    *,
    scale: int = 1,
    game_folder: Path | str | None = None,
) -> bytes:
    """Keep supersampling active through FH6 UV warp and vehicle-mask clipping.

    KFPS's canonical contract is 2048x1024. For quality testing we perform the
    exact same flip/transpose/origin transform on an integer supersampled atlas,
    upscale the authoritative vehicle mask, then downsample only the final cropped
    projection. This avoids throwing away supersampling before the BILINEAR warp.
    """
    import numpy as np
    from PIL import Image

    scale = int(scale)
    if scale < 1 or scale > 4:
        raise ExactLiveryPreviewError("현재 검증된 projection supersampling 범위는 1~4배입니다.")

    game = Path(game_folder).resolve() if game_folder is not None else require_fh6_game_folder()
    render_contract, slot, base_mask, projection, _mask_hash = _projection_record(
        section, int(car_id), game
    )
    base_width, base_height = tuple(render_contract.ATLAS_SIZE)
    target_size = (base_width * scale, base_height * scale)

    try:
        with Image.open(io.BytesIO(png_bytes)) as source:
            artwork = source.convert("RGBA")
        if artwork.size != target_size:
            raise ExactLiveryPreviewError(
                f"리버리 section canvas 크기가 올바르지 않습니다: {artwork.size}; 예상 {target_size}"
            )

        if scale == 1:
            clipped = render_contract._masked_atlas_layer(artwork, base_mask, slot, projection)
            bounds = render_contract._projection_pixel_bounds(projection)
            surface_alpha = base_mask.convert("L").point(lambda value: (int(value) * 72) // 255)
            surface = Image.new("RGBA", clipped.size, (150, 154, 162, 0))
            surface.putalpha(surface_alpha)
            combined = Image.alpha_composite(surface, clipped).crop(bounds)
        else:
            x_origin = float(projection.get("xorigin", 0.0)) * scale
            y_origin = float(projection.get("yorigin", 0.0)) * scale
            affine = render_contract._atlas_to_local_affine(
                slot,
                target_size[0],
                target_size[1],
                x_origin,
                y_origin,
            )
            warped = artwork.transform(
                target_size,
                Image.Transform.AFFINE,
                affine,
                resample=Image.Resampling.BILINEAR,
                fillcolor=(0, 0, 0, 0),
            )
            mask = base_mask.convert("L").resize(target_size, Image.Resampling.BILINEAR)
            rgba = np.asarray(warped, dtype=np.uint8).copy()
            mask_values = np.asarray(mask, dtype=np.uint16)
            rgba[..., 3] = (
                (rgba[..., 3].astype(np.uint16) * mask_values + 127) // 255
            ).astype(np.uint8)
            clipped = Image.fromarray(rgba, mode="RGBA")

            base_bounds = render_contract._projection_pixel_bounds(projection)
            bounds = tuple(int(value * scale) for value in base_bounds)
            surface_alpha = mask.point(lambda value: (int(value) * 72) // 255)
            surface = Image.new("RGBA", target_size, (150, 154, 162, 0))
            surface.putalpha(surface_alpha)
            combined = Image.alpha_composite(surface, clipped).crop(bounds)

            final_size = (
                max(1, base_bounds[2] - base_bounds[0]),
                max(1, base_bounds[3] - base_bounds[1]),
            )
            combined = combined.resize(final_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        combined.save(buffer, format="PNG", compress_level=3)
        return buffer.getvalue()
    except ExactLiveryPreviewError:
        raise
    except Exception as exc:
        raise ExactLiveryPreviewError(
            f"{section} 영역에 차량별 projection mask를 적용하지 못했습니다: {exc}"
        ) from exc


def clear_exact_preview_cache() -> None:
    with _LOCK:
        _normalize_game_folder_cached.cache_clear()
        _discover_fh6_game_folder_cached.cache_clear()
        _vehicle_index.cache_clear()
        _vehicle_masks_cached.cache_clear()
        _raster_resolver_cached.cache_clear()
