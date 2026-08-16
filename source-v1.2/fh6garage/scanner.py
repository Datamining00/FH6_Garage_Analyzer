from __future__ import annotations

import re
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from .car_db import CarDatabase
from .models import (
    CarContentSummary,
    LiveryRecord,
    ScanResult,
    TuningRecord,
)
from .parsers import ParseError, parse_save_metadata, read_header_file


_CONTAINER_RE = re.compile(r"^(?P<kind>BaseLivery|SoulBoundLivery|Livery|Tuning)_", re.IGNORECASE)
_CONTAINER_CAR_ID_RE = re.compile(
    r"^(?P<kind>BaseLivery|SoulBoundLivery|Livery|Tuning)_(?P<car_id>\d+)(?:_|$)",
    re.IGNORECASE,
)


class SaveLayoutError(ValueError):
    pass


def _file_created_timestamp(path: Path) -> float | None:
    """Read local filesystem creation time as a download-time proxy."""
    try:
        stat = path.stat()
    except OSError:
        return None
    value = getattr(stat, "st_birthtime", stat.st_ctime)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _numeric_version_dirs(path: Path) -> list[Path]:
    result = [p for p in path.iterdir() if p.is_dir() and p.name.isdigit() and (p / "ContainersRoot").is_dir()]
    return sorted(result, key=lambda p: int(p.name), reverse=True)


def _container_car_id(container_name: str, expected_kind: str) -> int | None:
    """Return the CarOrdinal encoded in a standard FH6 content-container name.

    FH6 containers use names such as ``Livery_1229_20260816092247``.  Some
    downloaded liveries (notably liveries obtained while viewing another
    player's car in a convoy/car meet) have a header tail whose four bytes at
    the legacy CarId position are not the CarOrdinal.  The container name still
    carries the correct ordinal, so it is a reliable recovery source when the
    header value is unknown or disagrees with the known vehicle database.
    """
    match = _CONTAINER_CAR_ID_RE.match(container_name)
    if not match or match.group("kind").lower() != expected_kind.lower():
        return None
    try:
        car_id = int(match.group("car_id"))
    except ValueError:
        return None
    return car_id if car_id > 0 else None


def _resolve_car_id(container_name: str, kind: str, header_car_id: int | None, car_db: CarDatabase) -> int | None:
    """Resolve CarOrdinal without replacing valid legacy-header results.

    The original header parser is kept for backwards compatibility.  A
    container-name ordinal is preferred only when it is known to the effective
    car database and the parsed header value is missing, unknown, or different.
    This fixes the observed community-livery format while avoiding guesses for
    containers whose naming scheme cannot be verified.
    """
    container_car_id = _container_car_id(container_name, kind)
    if container_car_id is None:
        return header_car_id

    if car_db.is_known(container_car_id):
        if header_car_id is None or not car_db.is_known(header_car_id) or header_car_id != container_car_id:
            return container_car_id

    return header_car_id


def resolve_layout(selected: Path) -> tuple[Path, Path, str]:
    selected = selected.expanduser().resolve()
    if not selected.is_dir():
        raise SaveLayoutError("선택한 경로가 폴더가 아닙니다.")

    # Direct ContainersRoot selection.
    if selected.name.lower() == "containersroot":
        version_dir = selected.parent
        save_root = version_dir.parent
        return save_root, selected, version_dir.name

    # Version/current directory selection.
    if (selected / "ContainersRoot").is_dir():
        save_root = selected.parent
        return save_root, selected / "ContainersRoot", selected.name

    # Save root selection. Prefer current to avoid double-counting current + numbered version.
    if (selected / "current" / "ContainersRoot").is_dir():
        return selected, selected / "current" / "ContainersRoot", "current"

    versions = _numeric_version_dirs(selected)
    if versions:
        return selected, versions[0] / "ContainersRoot", versions[0].name

    # One level above a save root, useful when selecting the PGS parent directory.
    for child in sorted((p for p in selected.iterdir() if p.is_dir()), key=lambda p: p.name):
        if (child / "current" / "ContainersRoot").is_dir():
            return child, child / "current" / "ContainersRoot", "current"
        versions = _numeric_version_dirs(child)
        if versions:
            return child, versions[0] / "ContainersRoot", versions[0].name

    raise SaveLayoutError("ContainersRoot를 찾지 못했습니다. FH6 세이브 루트/current/버전 폴더 중 하나를 선택하세요.")


def _detect_thumbnail(container: Path, tuning: bool) -> Path | None:
    names = ("Thumb.png", "thumb.png") if tuning else ("bigThumb.webp", "BigThumb.webp")
    for name in names:
        candidate = container / name
        if candidate.is_file():
            return candidate
    return None


def scan_save(selected_path: Path, car_db: CarDatabase) -> ScanResult:
    save_root, containers_root, active_version = resolve_layout(selected_path)
    metadata = parse_save_metadata(selected_path.resolve(), save_root, containers_root, active_version)
    warnings: list[str] = []
    liveries: list[LiveryRecord] = []
    tunings: list[TuningRecord] = []
    counts: Counter[str] = Counter()

    for container in sorted((p for p in containers_root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        prefix = container.name.split("_", 1)[0]
        counts[prefix] += 1
        match = _CONTAINER_RE.match(container.name)
        if match:
            raw_kind = match.group("kind")
            kind_map = {
                "baselivery": "BaseLivery",
                "soulboundlivery": "SoulBoundLivery",
                "livery": "Livery",
                "tuning": "Tuning",
            }
            kind = kind_map[raw_kind.lower()]
            header_path = container / "header"
            if not header_path.is_file():
                warnings.append(f"{container.name}: header 없음")
                continue
            try:
                header = read_header_file(header_path, kind)
            except (OSError, ParseError) as exc:
                warnings.append(f"{container.name}: header 파싱 실패 ({exc})")
                continue

            parsed_car_id = header.car_id
            resolved_car_id = _resolve_car_id(container.name, kind, parsed_car_id, car_db)
            if resolved_car_id != parsed_car_id:
                header.car_id = resolved_car_id
                warnings.append(
                    f"{container.name}: header Car ID {parsed_car_id} 대신 컨테이너 CarOrdinal {resolved_car_id} 사용"
                )

            if kind == "Tuning":
                data_path = container / "Data"
                tunings.append(
                    TuningRecord(
                        container_name=container.name,
                        container_path=container,
                        header=header,
                        thumbnail_path=_detect_thumbnail(container, tuning=True),
                        data_path=data_path if data_path.is_file() else None,
                        data_size=data_path.stat().st_size if data_path.is_file() else 0,
                        downloaded_at=(
                            _file_created_timestamp(data_path)
                            if data_path.is_file()
                            else None
                        ),
                    )
                )
            else:
                livery_path = container / "C_livery"
                liveries.append(
                    LiveryRecord(
                        container_name=container.name,
                        container_path=container,
                        kind=kind,
                        header=header,
                        thumbnail_path=_detect_thumbnail(container, tuning=False),
                        livery_path=livery_path if livery_path.is_file() else None,
                        downloaded_at=(
                            _file_created_timestamp(livery_path)
                            if livery_path.is_file()
                            else None
                        ),
                        content_sha256=(
                            _file_sha256(livery_path)
                            if livery_path.is_file()
                            else ""
                        ),
                    )
                )
            continue

    by_car: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in liveries:
        if record.car_id is None:
            continue
        if record.kind == "Livery":
            by_car[record.car_id]["livery"] += 1
        elif record.kind == "BaseLivery":
            by_car[record.car_id]["base"] += 1
        elif record.kind == "SoulBoundLivery":
            by_car[record.car_id]["soul"] += 1
    for record in tunings:
        if record.car_id is not None:
            by_car[record.car_id]["tuning"] += 1

    summaries: list[CarContentSummary] = []
    for car_id in sorted(by_car):
        info = car_db.get(car_id)
        item = by_car[car_id]
        # BaseLivery/SoulBoundLivery are intentionally hidden from the user-facing
        # dashboard and do not create a row when they are the only content.
        if item.get("livery", 0) == 0 and item.get("tuning", 0) == 0:
            continue
        summaries.append(
            CarContentSummary(
                car_id=car_id,
                label=info.label or f"Car ID {car_id}",
                livery_count=item.get("livery", 0),
                tuning_count=item.get("tuning", 0),
                base_livery_count=item.get("base", 0),
                soulbound_count=item.get("soul", 0),
            )
        )

    return ScanResult(
        metadata=metadata,
        liveries=liveries,
        tunings=tunings,
        car_summaries=summaries,
        container_counts=dict(counts),
        warnings=warnings,
    )
