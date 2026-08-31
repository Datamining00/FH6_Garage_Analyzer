from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Literal

from .car_db import CarDatabase
from .i18n import tr
from .models import (
    CarContentSummary,
    HeaderInfo,
    LiveryRecord,
    ScanResult,
    TuningRecord,
)
from .parsers import ParseError, parse_save_metadata, read_header_file
from .performance_metrics import PerformanceMetrics
from .runtime_policy import RuntimePolicy, detect_runtime_policy
from .scan_backend import ScanJob, SequentialScanBackend, ThreadedScanBackend
from .scan_cache import FileAnalysisCache

_CONTAINER_RE = re.compile(r"^(?P<kind>BaseLivery|SoulBoundLivery|Livery|Tuning)_", re.IGNORECASE)
_CONTAINER_CAR_ID_RE = re.compile(
    r"^(?P<kind>BaseLivery|SoulBoundLivery|Livery|Tuning)_(?P<car_id>\d+)(?:_|$)",
    re.IGNORECASE,
)


class SaveLayoutError(ValueError):
    pass


@dataclass(slots=True)
class _ContainerAnalysis:
    job: ScanJob
    header: HeaderInfo | None = None
    thumbnail_path: Path | None = None
    content_path: Path | None = None
    content_size: int = 0
    downloaded_at: float | None = None
    content_sha256: str = ""
    failure: str = ""
    failure_detail: str = ""


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


def _safe_file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size) if path.is_file() else 0
    except OSError:
        return 0


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

    if car_db.is_known(container_car_id) and (
        header_car_id is None
        or not car_db.is_known(header_car_id)
        or header_car_id != container_car_id
    ):
        return container_car_id

    return header_car_id


def resolve_layout(selected: Path) -> tuple[Path, Path, str]:
    selected = selected.expanduser().resolve()
    if not selected.is_dir():
        raise SaveLayoutError(tr("scanner.invalid_folder"))

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

    raise SaveLayoutError(tr("scanner.containers_missing"))


def _detect_thumbnail(container: Path, tuning: bool) -> Path | None:
    names = ("Thumb.png", "thumb.png") if tuning else ("bigThumb.webp", "BigThumb.webp")
    for name in names:
        candidate = container / name
        if candidate.is_file():
            return candidate
    return None


def _canonical_kind(raw_kind: str) -> str:
    return {
        "baselivery": "BaseLivery",
        "soulboundlivery": "SoulBoundLivery",
        "livery": "Livery",
        "tuning": "Tuning",
    }[raw_kind.casefold()]


def _job_estimated_bytes(container: Path, kind: str) -> int:
    content_name = "Data" if kind == "Tuning" else "C_livery"
    return _safe_file_size(container / "header") + _safe_file_size(
        container / content_name
    )


def _analyze_container(
    job: ScanJob,
    cache: FileAnalysisCache,
) -> _ContainerAnalysis:
    """Read one container without touching Qt or mutating FH6 content."""

    container = job.container
    header_path = container / "header"
    if not header_path.is_file():
        return _ContainerAnalysis(job=job, failure="header_missing")

    header = cache.get_header(header_path, job.kind)
    if header is None:
        try:
            header = read_header_file(header_path, job.kind)
        except (OSError, ParseError) as exc:
            return _ContainerAnalysis(
                job=job,
                failure="header_parse_failed",
                failure_detail=str(exc),
            )
        cache.put_header(header_path, job.kind, header)

    tuning = job.kind == "Tuning"
    content_path = container / ("Data" if tuning else "C_livery")
    if not content_path.is_file():
        content_path = None

    digest = ""
    # Only ordinary My Designs liveries participate in duplicate-content
    # grouping. BaseLivery and SoulBoundLivery payload hashes were calculated
    # during every initial scan but never consumed, causing avoidable reads of
    # every C_livery file.
    if job.kind == "Livery" and content_path is not None:
        digest = cache.get_sha256(content_path) or ""
        if not digest:
            digest = _file_sha256(content_path)
            if digest:
                cache.put_sha256(content_path, digest)

    return _ContainerAnalysis(
        job=job,
        header=header,
        thumbnail_path=_detect_thumbnail(container, tuning=tuning),
        content_path=content_path,
        content_size=_safe_file_size(content_path) if content_path is not None else 0,
        downloaded_at=(
            _file_created_timestamp(content_path)
            if content_path is not None
            else None
        ),
        content_sha256=digest,
    )


def _analyze_container_legacy(job: ScanJob) -> _ContainerAnalysis:
    """Original no-cache file path retained as the final compatibility fallback."""

    container = job.container
    header_path = container / "header"
    if not header_path.is_file():
        return _ContainerAnalysis(job=job, failure="header_missing")
    try:
        header = read_header_file(header_path, job.kind)
    except (OSError, ParseError) as exc:
        return _ContainerAnalysis(
            job=job,
            failure="header_parse_failed",
            failure_detail=str(exc),
        )

    tuning = job.kind == "Tuning"
    content_path = container / ("Data" if tuning else "C_livery")
    if not content_path.is_file():
        content_path = None
    return _ContainerAnalysis(
        job=job,
        header=header,
        thumbnail_path=_detect_thumbnail(container, tuning=tuning),
        content_path=content_path,
        content_size=_safe_file_size(content_path) if content_path is not None else 0,
        downloaded_at=(
            _file_created_timestamp(content_path)
            if content_path is not None
            else None
        ),
        content_sha256=(
            _file_sha256(content_path)
            if job.kind == "Livery" and content_path is not None
            else ""
        ),
    )


def _select_scan_backend(
    policy: RuntimePolicy,
    jobs: list[ScanJob],
    requested: Literal["auto", "sequential", "threaded"],
):
    if requested == "sequential":
        return SequentialScanBackend[_ContainerAnalysis]()
    if requested == "threaded":
        return ThreadedScanBackend[_ContainerAnalysis](policy.scan_workers)

    total_bytes = sum(max(0, job.estimated_bytes) for job in jobs)
    if (
        policy.scan_workers <= 1
        or len(jobs) < policy.parallel_scan_min_items
        or total_bytes < policy.parallel_scan_min_bytes
    ):
        return SequentialScanBackend[_ContainerAnalysis]()
    return ThreadedScanBackend[_ContainerAnalysis](policy.scan_workers)


def _enumerate_scan_jobs(
    containers_root: Path,
    metrics: PerformanceMetrics,
) -> tuple[list[ScanJob], set[Path], Counter[str]]:
    """Enumerate supported content containers and cache-tracked source paths."""

    jobs: list[ScanJob] = []
    active_cache_paths: set[Path] = set()
    counts: Counter[str] = Counter()

    with metrics.measure("scan.enumerate"):
        containers = sorted(
            (path for path in containers_root.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        )

    for container in containers:
        prefix = container.name.split("_", 1)[0]
        counts[prefix] += 1
        match = _CONTAINER_RE.match(container.name)
        if not match:
            continue

        kind = _canonical_kind(match.group("kind"))
        jobs.append(
            ScanJob(
                container=container,
                kind=kind,
                estimated_bytes=_job_estimated_bytes(container, kind),
            )
        )

        header_path = container / "header"
        if header_path.is_file():
            active_cache_paths.add(header_path)
        if kind != "Tuning":
            livery_path = container / "C_livery"
            if livery_path.is_file():
                active_cache_paths.add(livery_path)

    return jobs, active_cache_paths, counts


def _run_container_analyses(
    jobs: list[ScanJob],
    policy: RuntimePolicy,
    requested_backend: Literal["auto", "sequential", "threaded"],
    cache: FileAnalysisCache,
    metrics: PerformanceMetrics,
) -> list[_ContainerAnalysis]:
    """Run the selected scan backend and preserve the legacy fallback contract."""

    selected_backend = _select_scan_backend(policy, jobs, requested_backend)
    metrics.set("scan_backend", selected_backend.name)
    metrics.set("scan_workers", selected_backend.workers)
    metrics.set("scan_jobs", len(jobs))
    metrics.set(
        "scan_estimated_bytes",
        sum(max(0, job.estimated_bytes) for job in jobs),
    )

    analyze = lambda job: _analyze_container(job, cache)
    try:
        with metrics.measure("scan.analyze"):
            return selected_backend.run(jobs, analyze)
    except Exception as exc:  # noqa: BLE001 - backend failures require fallback
        # A backend implementation or executor failure must not make FH6 saves
        # unreadable on an otherwise supported machine.
        metrics.set("scan_fallback_used", True)
        metrics.set("scan_fallback_error", type(exc).__name__)
        fallback = SequentialScanBackend[_ContainerAnalysis]()
        metrics.set("scan_backend", fallback.name)
        metrics.set("scan_workers", 1)
        with metrics.measure("scan.fallback_analyze"):
            return fallback.run(jobs, _analyze_container_legacy)


def _aggregate_container_analyses(
    analyses: list[_ContainerAnalysis],
    car_db: CarDatabase,
    metrics: PerformanceMetrics,
) -> tuple[list[LiveryRecord], list[TuningRecord], list[str]]:
    """Resolve identities and convert low-level analyses into public records."""

    warnings: list[str] = []
    liveries: list[LiveryRecord] = []
    tunings: list[TuningRecord] = []

    with metrics.measure("scan.aggregate"):
        for analysis in analyses:
            container = analysis.job.container
            kind = analysis.job.kind
            if analysis.failure == "header_missing":
                warnings.append(
                    tr("scanner.header_missing", container=container.name)
                )
                continue
            if analysis.failure == "header_parse_failed":
                warnings.append(
                    tr(
                        "scanner.header_parse_failed",
                        container=container.name,
                        error=analysis.failure_detail,
                    )
                )
                continue

            header = analysis.header
            if header is None:
                continue

            parsed_car_id = (
                header.parsed_car_id
                if header.parsed_car_id is not None
                else header.car_id
            )
            resolved_car_id = _resolve_car_id(
                container.name,
                kind,
                parsed_car_id,
                car_db,
            )
            # Keep the parser/cache object as parser-owned data. The ScanResult
            # receives a distinct resolved header so compatibility recovery no
            # longer mutates analysis-layer metadata in place.
            header = replace(
                header,
                car_id=resolved_car_id,
                parsed_car_id=parsed_car_id,
            )
            if resolved_car_id != parsed_car_id:
                warnings.append(
                    tr(
                        "scanner.car_id_fallback",
                        container=container.name,
                        header_id=parsed_car_id,
                        car_id=resolved_car_id,
                    )
                )

            if kind == "Tuning":
                tunings.append(
                    TuningRecord(
                        container_name=container.name,
                        container_path=container,
                        header=header,
                        thumbnail_path=analysis.thumbnail_path,
                        data_path=analysis.content_path,
                        data_size=analysis.content_size,
                        downloaded_at=analysis.downloaded_at,
                    )
                )
            else:
                liveries.append(
                    LiveryRecord(
                        container_name=container.name,
                        container_path=container,
                        kind=kind,
                        header=header,
                        thumbnail_path=analysis.thumbnail_path,
                        livery_path=analysis.content_path,
                        downloaded_at=analysis.downloaded_at,
                        content_sha256=analysis.content_sha256,
                    )
                )

    return liveries, tunings, warnings


def _build_car_summaries(
    liveries: list[LiveryRecord],
    tunings: list[TuningRecord],
    car_db: CarDatabase,
) -> list[CarContentSummary]:
    """Build the dashboard-visible per-car saved-content summary."""

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
    return summaries


def scan_save(
    selected_path: Path,
    car_db: CarDatabase,
    *,
    runtime_policy: RuntimePolicy | None = None,
    cache_base_dir: Path | None = None,
    backend: Literal["auto", "sequential", "threaded"] = "auto",
) -> ScanResult:
    """Scan one FH6 save with a compatibility-first adaptive I/O backend.

    ``backend`` and ``cache_base_dir`` are primarily diagnostic/test controls.
    Normal callers use automatic policy selection. Any unexpected threaded
    backend failure is retried through the original sequential semantics.

    The public orchestration order is intentionally explicit:
    layout/metadata -> enumerate -> analyze -> resolve/aggregate -> cache ->
    dashboard summary. Helper extraction does not change the scan contract.
    """

    if backend not in {"auto", "sequential", "threaded"}:
        raise ValueError(f"unsupported scan backend: {backend}")

    started = perf_counter()
    metrics = PerformanceMetrics()
    policy = runtime_policy or detect_runtime_policy()

    with metrics.measure("scan.resolve_layout"):
        save_root, containers_root, active_version = resolve_layout(selected_path)
    with metrics.measure("scan.metadata"):
        metadata = parse_save_metadata(
            selected_path.resolve(),
            save_root,
            containers_root,
            active_version,
        )

    cache = FileAnalysisCache(save_root, base_dir=cache_base_dir)
    jobs, active_cache_paths, counts = _enumerate_scan_jobs(
        containers_root,
        metrics,
    )
    analyses = _run_container_analyses(
        jobs,
        policy,
        backend,
        cache,
        metrics,
    )
    liveries, tunings, warnings = _aggregate_container_analyses(
        analyses,
        car_db,
        metrics,
    )

    with metrics.measure("scan.cache_save"):
        cache.prune_to_paths(active_cache_paths)
        cache.save()

    summaries = _build_car_summaries(liveries, tunings, car_db)

    metrics.timings_ms["scan.total"] = round(
        (perf_counter() - started) * 1000.0,
        3,
    )
    cache_stats = cache.stats()
    for key, value in cache_stats.items():
        metrics.set(key, value)

    return ScanResult(
        metadata=metadata,
        liveries=liveries,
        tunings=tunings,
        car_summaries=summaries,
        container_counts=dict(counts),
        warnings=warnings,
        diagnostics={
            "runtime_policy": policy.as_dict(),
            "scan": metrics.snapshot(),
        },
    )
