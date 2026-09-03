from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

CAR_CLIP_RE = re.compile(r"(?:^|/)carclips_(\d+)\.clipd$", re.IGNORECASE)


class VehicleAssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class VehicleAsset:
    car_id: int
    model_code: str
    archive_path: str
    archive_name: str
    carbin_entries: tuple[str, ...]
    mask_xml: str | None
    mask_assets: tuple[str, ...]


def _candidate_car_dirs(root: Path) -> Iterable[Path]:
    yield root / "Content" / "media" / "cars"
    yield root / "media" / "cars"
    if root.name.casefold() == "content":
        yield root / "media" / "cars"
    yield root


def resolve_cars_dir(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    seen: set[Path] = set()
    for candidate in _candidate_car_dirs(root):
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_dir() and any(candidate.glob("*.zip")):
            return candidate
    raise VehicleAssetError("FH6 media/cars folder could not be located.")


def _safe_iterdir(path: Path) -> Iterable[Path]:
    try:
        yield from path.iterdir()
    except (OSError, PermissionError):
        return


def _logical_drive_roots() -> tuple[Path, ...]:
    if os.name != "nt":
        return ()
    try:
        import ctypes
        mask = int(ctypes.windll.kernel32.GetLogicalDrives())
    except Exception:
        return ()
    return tuple(Path(f"{chr(65 + i)}:/") for i in range(26) if mask & (1 << i))


def _steam_roots() -> tuple[Path, ...]:
    if os.name != "nt":
        return ()
    roots: list[Path] = []
    try:
        import winreg
        probes = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        )
        for hive, key_name, value_name in probes:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    roots.append(Path(str(value)))
            except OSError:
                pass
    except Exception:
        pass
    for drive in _logical_drive_roots():
        roots.extend((drive / "Steam", drive / "SteamLibrary"))
    libraries: list[Path] = []
    seen: set[str] = set()
    path_re = re.compile(r'^\s*"path"\s*"([^"]+)"', re.IGNORECASE)
    for steam_root in roots:
        try:
            root = steam_root.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(str(root))
        if key in seen:
            continue
        seen.add(key)
        libraries.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            match = path_re.match(line)
            if not match:
                continue
            try:
                library = Path(match.group(1).replace("\\\\", "\\")).expanduser().resolve()
            except OSError:
                continue
            lib_key = os.path.normcase(str(library))
            if lib_key not in seen:
                seen.add(lib_key)
                libraries.append(library)
    return tuple(libraries)


def _content_dir_from_path(path: Path) -> Path | None:
    try:
        root = path.expanduser().resolve()
    except OSError:
        return None
    if root.name.casefold() == "content":
        return root
    content = root / "Content"
    if content.is_dir():
        return content
    if root.name.casefold() == "cars" and root.parent.name.casefold() == "media":
        parent = root.parent.parent
        if parent.name.casefold() == "content":
            return parent
    return None


def game_root_from_path(path: str | Path) -> Path:
    cars_dir = resolve_cars_dir(path)
    content = _content_dir_from_path(cars_dir)
    if content is not None and content.name.casefold() == "content":
        return content.parent
    return cars_dir.parent.parent


def _cars_dir_has_fh6_archive(cars_dir: Path, probe_limit: int = 24) -> bool:
    for index, archive in enumerate(sorted(cars_dir.glob("*.zip"), key=lambda p: p.name.casefold())):
        if index >= probe_limit:
            break
        try:
            with zipfile.ZipFile(archive) as bundle:
                if any(CAR_CLIP_RE.search(name.replace("\\", "/")) for name in bundle.namelist()):
                    return True
        except (OSError, zipfile.BadZipFile):
            continue
    return False


def is_full_fh6_install(path: str | Path) -> bool:
    try:
        cars_dir = resolve_cars_dir(path)
    except VehicleAssetError:
        return False
    content = _content_dir_from_path(cars_dir)
    if content is None or content.name.casefold() != "content":
        return False
    try:
        return cars_dir.resolve() == (content / "media" / "cars").resolve() and _cars_dir_has_fh6_archive(cars_dir)
    except OSError:
        return False


def _installation_candidates() -> Iterable[Path]:
    for name in ("FH6_GAME_DIR", "FORZA_HORIZON_6_DIR"):
        value = os.environ.get(name)
        if value:
            yield Path(value)
    if os.name != "nt":
        return
    for drive in _logical_drive_roots():
        xbox = drive / "XboxGames"
        direct = xbox / "Forza Horizon 6"
        if direct.is_dir():
            yield direct
        for child in _safe_iterdir(xbox):
            if child.is_dir():
                yield child
    for library in _steam_roots():
        common = library / "steamapps" / "common"
        direct = common / "Forza Horizon 6"
        if direct.is_dir():
            yield direct
        for child in _safe_iterdir(common):
            if child.is_dir():
                yield child


@lru_cache(maxsize=1)
def detect_fh6_installation() -> Path | None:
    seen: set[str] = set()
    for candidate in _installation_candidates():
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if is_full_fh6_install(resolved):
            return game_root_from_path(resolved)
    return None


def load_vehicle_asset(archive: str | Path) -> VehicleAsset:
    archive = Path(archive).expanduser().resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = tuple(name.replace("\\", "/") for name in bundle.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise VehicleAssetError(f"Vehicle archive could not be read: {archive.name}: {exc}") from exc
    car_id = None
    for name in names:
        match = CAR_CLIP_RE.search(name)
        if match:
            car_id = int(match.group(1))
            break
    if car_id is None:
        raise VehicleAssetError(f"Vehicle archive has no carclips_<CarID>.clipd identity: {archive.name}")
    carbin_entries = tuple(sorted((name for name in names if name.casefold().endswith(".carbin")), key=str.casefold))
    mask_xml = next((name for name in names if name.casefold() == "liverymasks/masks.xml"), None)
    mask_assets = tuple(sorted((name for name in names if name.casefold().startswith("liverymasks/") and name.casefold().endswith(".swatchbin")), key=str.casefold))
    return VehicleAsset(car_id, archive.stem, str(archive), archive.name, carbin_entries, mask_xml, mask_assets)


def preferred_carbin_entry(asset: VehicleAsset) -> str | None:
    entries = tuple(asset.carbin_entries)
    if len(entries) == 1:
        return entries[0]
    if not entries:
        return None
    targets = {f"{asset.model_code.casefold()}.carbin", f"{Path(asset.archive_name).stem.casefold()}.carbin"}
    exact = [entry for entry in entries if Path(entry.replace("\\", "/")).name.casefold() in targets]
    if len(exact) == 1:
        return exact[0]
    root_level = [entry for entry in entries if "/" not in entry.replace("\\", "/").strip("/")]
    return root_level[0] if len(root_level) == 1 else None


@lru_cache(maxsize=4)
def _asset_index(cars_dir_text: str) -> dict[int, VehicleAsset]:
    cars_dir = Path(cars_dir_text)
    result: dict[int, VehicleAsset] = {}
    for archive in sorted(cars_dir.glob("*.zip"), key=lambda p: p.name.casefold()):
        try:
            asset = load_vehicle_asset(archive)
        except VehicleAssetError:
            continue
        result.setdefault(asset.car_id, asset)
    return result


def find_vehicle_asset(game_root: str | Path, car_id: int) -> VehicleAsset:
    cars_dir = resolve_cars_dir(game_root)
    asset = _asset_index(str(cars_dir)).get(int(car_id))
    if asset is None:
        raise VehicleAssetError(f"Car ID {car_id} was not found in the installed FH6 vehicle archives.")
    return asset
