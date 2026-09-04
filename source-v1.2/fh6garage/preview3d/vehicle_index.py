from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

CAR_CLIP_RE = re.compile(r"(?:^|/)carclips_(\d+)\.clipd$", re.IGNORECASE)


class VehicleIndexError(RuntimeError):
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
    archive_variants: tuple[str, ...] = ()
    duplicate_archives_identical: bool = True


def _candidate_car_dirs(root: Path) -> Iterable[Path]:
    # Prefer canonical installed-game layouts before treating the selected path
    # itself as an offline cars directory. This avoids an unrelated ZIP at the
    # game root shadowing Content/media/cars.
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
    raise VehicleIndexError("FH6 media/cars folder could not be located below the selected path.")



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
    roots: list[Path] = []
    for index in range(26):
        if mask & (1 << index):
            roots.append(Path(f"{chr(65 + index)}:/"))
    return tuple(roots)


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

    # Common portable/non-default Steam library roots. This is intentionally
    # shallow; the detector never recursively crawls a drive.
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
            raw = match.group(1).replace("\\\\", "\\")
            try:
                library = Path(raw).expanduser().resolve()
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
    """Return the installation root for a validated game/Content/cars path."""
    cars_dir = resolve_cars_dir(path)
    content = _content_dir_from_path(cars_dir)
    if content is not None and content.name.casefold() == "content":
        return content.parent
    return cars_dir.parent.parent



def _cars_dir_has_fh6_archive(cars_dir: Path, probe_limit: int = 24) -> bool:
    """Confirm that a candidate cars directory actually contains FH6 car identity data."""
    for index, archive in enumerate(sorted(cars_dir.glob("*.zip"), key=lambda p: p.name.casefold())):
        if index >= probe_limit:
            break
        try:
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    if CAR_CLIP_RE.search(name.replace("\\", "/")):
                        return True
        except (OSError, zipfile.BadZipFile):
            continue
    return False

def is_full_fh6_install(path: str | Path) -> bool:
    """Validate an FH6 installation root without requiring optional livery assets.

    The authoritative installation signal for vehicle discovery is a real
    Content/media/cars tree. Offline one-car folders do not have a Content root
    and therefore cannot override an installed game. Decals.zip is intentionally
    not mandatory because partial/offline installations may omit it.
    """
    try:
        cars_dir = resolve_cars_dir(path)
    except VehicleIndexError:
        return False
    content = _content_dir_from_path(cars_dir)
    if content is None or content.name.casefold() != "content":
        return False
    try:
        expected = (content / "media" / "cars").resolve()
        return cars_dir.resolve() == expected and _cars_dir_has_fh6_archive(cars_dir)
    except OSError:
        return False


def _installation_candidates(preferred: str | Path | None = None) -> Iterable[Path]:
    if preferred:
        yield Path(preferred)
    for name in ("FH6_GAME_DIR", "FORZA_HORIZON_6_DIR"):
        value = os.environ.get(name)
        if value:
            yield Path(value)

    if os.name != "nt":
        return

    # Xbox app installs are normally direct children of XboxGames. Scan only
    # one level and validate by the actual FH6 content layout.
    for drive in _logical_drive_roots():
        xbox = drive / "XboxGames"
        direct = xbox / "Forza Horizon 6"
        if direct.is_dir():
            yield direct
        for child in _safe_iterdir(xbox):
            if child.is_dir():
                yield child

    # Steam: discover registered libraries, then inspect only immediate game
    # directories under steamapps/common.
    for library in _steam_roots():
        common = library / "steamapps" / "common"
        direct = common / "Forza Horizon 6"
        if direct.is_dir():
            yield direct
        for child in _safe_iterdir(common):
            if child.is_dir():
                yield child


def detect_fh6_installation(preferred: str | Path | None = None) -> Path | None:
    """Find a full FH6 install without recursively scanning user disks."""
    seen: set[str] = set()
    for candidate in _installation_candidates(preferred):
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if not is_full_fh6_install(resolved):
            continue
        try:
            return game_root_from_path(resolved)
        except VehicleIndexError:
            continue
    return None

def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_vehicle_asset(archive: str | Path) -> VehicleAsset:
    archive = Path(archive).expanduser().resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = tuple(bundle.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise VehicleIndexError(f"Vehicle archive could not be read: {archive.name}: {exc}") from exc
    normalized = [name.replace("\\", "/") for name in names]
    car_id = None
    for name in normalized:
        match = CAR_CLIP_RE.search(name)
        if match:
            car_id = int(match.group(1))
            break
    if car_id is None:
        raise VehicleIndexError(f"Vehicle archive has no carclips_<CarID>.clipd identity: {archive.name}")
    carbin_entries = tuple(sorted(
        (name for name in normalized if name.casefold().endswith(".carbin")),
        key=str.casefold,
    ))
    mask_xml = next((name for name in normalized if name.casefold() == "liverymasks/masks.xml"), None)
    mask_assets = tuple(sorted((
        name for name in normalized
        if name.casefold().startswith("liverymasks/") and name.casefold().endswith(".swatchbin")
    ), key=str.casefold))
    return VehicleAsset(
        car_id=car_id,
        model_code=archive.stem,
        archive_path=str(archive),
        archive_name=archive.name,
        carbin_entries=carbin_entries,
        mask_xml=mask_xml,
        mask_assets=mask_assets,
        archive_variants=(str(archive),),
        duplicate_archives_identical=True,
    )


def preferred_carbin_entry(asset: VehicleAsset) -> str | None:
    """Return a structurally obvious root scene, otherwise require user choice."""
    entries = tuple(asset.carbin_entries)
    if len(entries) == 1:
        return entries[0]
    if not entries:
        return None
    targets = {f"{asset.model_code.casefold()}.carbin", f"{Path(asset.archive_name).stem.casefold()}.carbin"}
    exact = [entry for entry in entries if Path(entry.replace("\\", "/")).name.casefold() in targets]
    if len(exact) == 1:
        return exact[0]
    # A single root-level carbin is also unambiguous. Nested scenes are not
    # guessed between when more than one remains.
    root_level = [entry for entry in entries if "/" not in entry.replace("\\", "/").strip("/")]
    if len(root_level) == 1:
        return root_level[0]
    return None


def scan_vehicle_assets(path: str | Path) -> dict[int, VehicleAsset]:
    cars_dir = resolve_cars_dir(path)
    grouped: dict[int, list[VehicleAsset]] = {}

    for archive in sorted(cars_dir.glob("*.zip"), key=lambda p: p.name.casefold()):
        try:
            asset = load_vehicle_asset(archive)
        except VehicleIndexError:
            continue
        grouped.setdefault(asset.car_id, []).append(asset)

    result: dict[int, VehicleAsset] = {}
    for car_id, variants in sorted(grouped.items()):
        variants = sorted(variants, key=lambda item: item.archive_name.casefold())
        chosen = variants[0]
        variant_paths = tuple(item.archive_path for item in variants)
        identical = True
        if len(variants) > 1:
            hashes: set[str] = set()
            for item in variants:
                try:
                    hashes.add(_file_sha256(Path(item.archive_path)))
                except OSError:
                    hashes.add(f"unreadable:{item.archive_path}")
            identical = len(hashes) == 1
        result[car_id] = VehicleAsset(
            car_id=chosen.car_id,
            model_code=chosen.model_code,
            archive_path=chosen.archive_path,
            archive_name=chosen.archive_name,
            carbin_entries=chosen.carbin_entries,
            mask_xml=chosen.mask_xml,
            mask_assets=chosen.mask_assets,
            archive_variants=variant_paths,
            duplicate_archives_identical=identical,
        )
    return result


def write_index_json(index: dict[int, VehicleAsset], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "fh6_livery_3d_vehicle_index_v2",
        "vehicle_count": len(index),
        "vehicles": {str(k): asdict(v) for k, v in sorted(index.items())},
        "duplicate_car_ids": {
            str(k): list(v.archive_variants)
            for k, v in sorted(index.items())
            if len(v.archive_variants) > 1
        },
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
