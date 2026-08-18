from __future__ import annotations

import importlib
import io
import os
import sys
import threading
from functools import lru_cache
from pathlib import Path


KFPS_VENDOR_COMMIT = "8965780b8966e09d2f2a17e4d0684cdd44d7437c"


class ExactLiveryPreviewError(RuntimeError):
    """Raised when an exact local FH6 vehicle projection cannot be produced."""


_LOCK = threading.RLock()


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


def _normalize_game_folder(path: Path | str) -> Path:
    vehicle_assets, _render_contract, _raster_decals = _load_backend()
    try:
        return Path(vehicle_assets.normalize_fh6_game_folder(path)).resolve()
    except Exception as exc:
        raise ExactLiveryPreviewError(
            "선택한 폴더에서 FH6 차량 아카이브를 찾지 못했습니다. "
            "Forza Horizon 6 폴더 또는 Content 폴더를 선택해 주세요."
        ) from exc


def set_fh6_game_folder(path: Path | str) -> Path:
    normalized = _normalize_game_folder(path)
    preference = _saved_game_folder_path()
    preference.parent.mkdir(parents=True, exist_ok=True)
    temporary = preference.with_suffix(".tmp")
    temporary.write_text(str(normalized), encoding="utf-8")
    os.replace(temporary, preference)
    clear_exact_preview_cache()
    return normalized


def saved_fh6_game_folder() -> Path | None:
    value = _saved_game_folder_text()
    if not value:
        return None
    try:
        return _normalize_game_folder(value)
    except ExactLiveryPreviewError:
        return None


def configured_fh6_game_folder() -> Path | None:
    """Return a verified FH6 install root, preferring the user's explicit choice."""
    return _configured_game_folder_cached(
        os.environ.get("FH6_GAME_FOLDER", ""),
        _saved_game_folder_text(),
    )


def _saved_game_folder_text() -> str:
    preference = _saved_game_folder_path()
    try:
        return preference.read_text(encoding="utf-8").strip() if preference.is_file() else ""
    except OSError:
        return ""


@lru_cache(maxsize=4)
def _configured_game_folder_cached(environment_value: str, saved_value: str) -> Path | None:
    vehicle_assets, _render_contract, _raster_decals = _load_backend()
    for value in (environment_value.strip(), saved_value.strip()):
        if not value:
            continue
        try:
            return Path(vehicle_assets.normalize_fh6_game_folder(value)).resolve()
        except Exception:
            continue
    try:
        discovered = vehicle_assets.discover_fh6_game_folder()
    except Exception:
        discovered = None
    if discovered:
        try:
            return Path(vehicle_assets.normalize_fh6_game_folder(discovered)).resolve()
        except Exception:
            pass
    return None


def require_fh6_game_folder() -> Path:
    game_folder = configured_fh6_game_folder()
    if game_folder is None:
        raise ExactLiveryPreviewError(
            "원본과 일치하는 리버리 미리보기에는 로컬 FH6 설치 파일의 차량 projection mask가 필요합니다. "
            "이미지 창에서 'FH6 설치 폴더 지정'을 눌러 게임 폴더 또는 Content 폴더를 선택해 주세요."
        )
    return game_folder


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


@lru_cache(maxsize=4)
def _raster_resolver_cached(game_folder_text: str):
    _vehicle_assets, _render_contract, raster_decals = _load_backend()
    try:
        return raster_decals.FH6RasterDecalResolver(game_folder_text)
    except Exception as exc:
        raise ExactLiveryPreviewError(
            "FH6 내장 래스터 데칼 아카이브를 찾거나 읽지 못했습니다."
        ) from exc


def raster_resolver_for_game(game_folder: Path | str | None = None):
    game = Path(game_folder).resolve() if game_folder is not None else require_fh6_game_folder()
    return _raster_resolver_cached(str(game))


def apply_exact_vehicle_projection(
    png_bytes: bytes,
    section: str,
    car_id: int,
    *,
    game_folder: Path | str | None = None,
) -> bytes:
    """Apply the exact car-specific FH6 Masks.xml/swatch projection to one section.

    The incoming artwork is the canonical 2048x1024 FH6 section canvas. The
    result is warped with the car's projection origin/axis convention and clipped
    by the exact local LiveryMasks swatch. No approximate world projection and
    no generic body silhouette are substituted.
    """
    from PIL import Image

    game = Path(game_folder).resolve() if game_folder is not None else require_fh6_game_folder()
    _vehicle_assets, render_contract, _raster_decals = _load_backend()
    slot = getattr(render_contract, "SECTION_TO_SLOT", {}).get(str(section))
    if not slot:
        raise ExactLiveryPreviewError(f"지원하지 않는 FH6 livery section입니다: {section}")

    mask_record = _vehicle_masks(int(car_id), game).get(slot)
    if mask_record is None:
        raise ExactLiveryPreviewError(
            f"이 차량은 {section} 영역의 정확한 FH6 projection mask를 제공하지 않습니다."
        )
    mask, projection, _mask_hash = mask_record
    if mask.getbbox() is None:
        raise ExactLiveryPreviewError(
            f"이 차량의 {section} projection mask가 비어 있어 정확한 미리보기를 만들 수 없습니다."
        )

    try:
        with Image.open(io.BytesIO(png_bytes)) as source:
            artwork = source.convert("RGBA")
        if artwork.size != tuple(render_contract.ATLAS_SIZE):
            raise ExactLiveryPreviewError(
                f"리버리 section canvas 크기가 올바르지 않습니다: {artwork.size}"
            )
        clipped = render_contract._masked_atlas_layer(artwork, mask, slot, projection)
        bounds = render_contract._projection_pixel_bounds(projection)

        # Show the exact projection silhouette behind the artwork. The neutral
        # surface is a viewing aid only; its alpha is derived from the local FH6
        # vehicle mask, so oversized decals remain clipped at the game boundary.
        surface_alpha = mask.convert("L").point(lambda value: (int(value) * 72) // 255)
        surface = Image.new("RGBA", clipped.size, (150, 154, 162, 0))
        surface.putalpha(surface_alpha)
        combined = Image.alpha_composite(surface, clipped).crop(bounds)
        buffer = io.BytesIO()
        combined.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except ExactLiveryPreviewError:
        raise
    except Exception as exc:
        raise ExactLiveryPreviewError(
            f"{section} 영역에 차량별 projection mask를 적용하지 못했습니다: {exc}"
        ) from exc


def clear_exact_preview_cache() -> None:
    with _LOCK:
        _configured_game_folder_cached.cache_clear()
        _vehicle_index.cache_clear()
        _vehicle_masks_cached.cache_clear()
        _raster_resolver_cached.cache_clear()
