from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Iterable
import zipfile

from .tire_asset import TireAssetError, tire_library_dir


class TireFamilyExportError(RuntimeError):
    """Raised when native tire samples cannot be exported without touching game files."""


@dataclass(frozen=True)
class ExportedTireFamily:
    tire_model_name: str
    source_archive: str
    source_archive_sha256: str
    geometry_identity_sha256: str
    modelbin_entries: tuple[str, ...]
    modelbin_sha256: tuple[str, ...]
    exported_archive: str
    copied_archive_sha256: str
    copy_verified: bool

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["modelbin_entries"] = list(self.modelbin_entries)
        data["modelbin_sha256"] = list(self.modelbin_sha256)
        return data


@dataclass(frozen=True)
class SkippedDuplicateGeometry:
    tire_model_name: str
    archive_name: str
    geometry_identity_sha256: str
    representative_tire_model_name: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class TireFamilyExportReport:
    source_tires_dir: str
    output_dir: str
    bundle_path: str
    manifest_path: str
    requested_limit: int
    excluded_model_names: tuple[str, ...]
    inspected_archive_count: int
    exported_unique_geometry_count: int
    exported: tuple[ExportedTireFamily, ...]
    skipped_duplicate_geometry: tuple[SkippedDuplicateGeometry, ...]
    source_archives_read_only_unchanged: bool
    status: str
    production_mapping_enabled: bool
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_family_export_v1",
            "source_tires_dir": self.source_tires_dir,
            "output_dir": self.output_dir,
            "bundle_path": self.bundle_path,
            "manifest_path": self.manifest_path,
            "requested_limit": self.requested_limit,
            "excluded_model_names": list(self.excluded_model_names),
            "inspected_archive_count": self.inspected_archive_count,
            "exported_unique_geometry_count": self.exported_unique_geometry_count,
            "exported": [item.as_dict() for item in self.exported],
            "skipped_duplicate_geometry": [item.as_dict() for item in self.skipped_duplicate_geometry],
            "source_archives_read_only_unchanged": self.source_archives_read_only_unchanged,
            "status": self.status,
            "production_mapping_enabled": self.production_mapping_enabled,
            "limitations": list(self.limitations),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _tire_model_name_from_archive(path: Path) -> str:
    name = path.name
    lower = name.casefold()
    if not lower.startswith("tire_") or not lower.endswith(".zip"):
        raise TireFamilyExportError(f"not a native tire archive name: {name}")
    model = name[5:-4].strip()
    if not model:
        raise TireFamilyExportError(f"native tire archive has an empty model name: {name}")
    return model


def _archive_geometry_identity(
    archive: Path,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    before = _sha256(archive)
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            entries = sorted(
                (
                    item
                    for item in bundle.infolist()
                    if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
                ),
                key=lambda item: item.filename.casefold(),
            )
            if not entries:
                raise TireFamilyExportError(f"native tire archive contains no modelbin: {archive}")
            names: list[str] = []
            hashes: list[str] = []
            for item in entries:
                names.append(item.filename.replace("\\", "/"))
                hashes.append(hashlib.sha256(bundle.read(item)).hexdigest())
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireFamilyExportError(f"could not inspect native tire archive {archive}: {exc}") from exc

    after = _sha256(archive)
    if before != after:
        raise TireFamilyExportError(f"read-only inspection changed source tire archive: {archive}")
    canonical = "\n".join(sorted(hashes))
    geometry_identity = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    return geometry_identity, tuple(names), tuple(hashes)


def export_tire_family_samples_from_directory(
    tires_dir: str | Path,
    output_dir: str | Path,
    *,
    exclude_model_names: Iterable[str] = ("Slick",),
    limit: int = 5,
) -> TireFamilyExportReport:
    """Copy representative native tire ZIPs to a separate diagnostic bundle.

    Source archives are only opened for reading. Distinct family evidence is based on
    the set of modelbin byte hashes, not merely archive names.
    """
    source = Path(tires_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise TireFamilyExportError(f"native tire directory does not exist: {source}")
    requested_limit = int(limit)
    if requested_limit <= 0:
        raise TireFamilyExportError("limit must be greater than zero")
    if output.exists():
        raise TireFamilyExportError(f"output directory already exists: {output}")
    if _is_within(output, source):
        raise TireFamilyExportError("output directory must be outside the native FH6 tire library")

    excluded = tuple(sorted({str(value).strip() for value in exclude_model_names if str(value).strip()}, key=str.casefold))
    excluded_keys = {value.casefold() for value in excluded}
    try:
        archives = sorted(
            (
                path
                for path in source.iterdir()
                if path.is_file() and path.name.casefold().startswith("tire_") and path.name.casefold().endswith(".zip")
            ),
            key=lambda path: path.name.casefold(),
        )
    except (OSError, PermissionError) as exc:
        raise TireFamilyExportError(f"could not enumerate native tire library: {exc}") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=output.name + ".staging-", dir=output.parent))
    archive_dir = staging / "archives"
    archive_dir.mkdir()
    exported: list[ExportedTireFamily] = []
    duplicates: list[SkippedDuplicateGeometry] = []
    identity_owner: dict[str, str] = {}
    inspected = 0
    source_hashes_before: dict[Path, str] = {}
    try:
        for archive in archives:
            model_name = _tire_model_name_from_archive(archive)
            if model_name.casefold() in excluded_keys:
                continue
            inspected += 1
            source_hash = _sha256(archive)
            source_hashes_before[archive] = source_hash
            identity, modelbin_entries, modelbin_hashes = _archive_geometry_identity(archive)
            representative = identity_owner.get(identity)
            if representative is not None:
                duplicates.append(
                    SkippedDuplicateGeometry(
                        tire_model_name=model_name,
                        archive_name=archive.name,
                        geometry_identity_sha256=identity,
                        representative_tire_model_name=representative,
                    )
                )
                continue

            destination = archive_dir / archive.name
            if destination.exists():
                raise TireFamilyExportError(f"duplicate export destination: {destination}")
            shutil.copyfile(archive, destination)
            copied_hash = _sha256(destination)
            if copied_hash != source_hash:
                raise TireFamilyExportError(f"copied archive hash mismatch: {archive.name}")
            if _sha256(archive) != source_hash:
                raise TireFamilyExportError(f"source archive changed during copy: {archive}")

            identity_owner[identity] = model_name
            exported.append(
                ExportedTireFamily(
                    tire_model_name=model_name,
                    source_archive=str(archive),
                    source_archive_sha256=source_hash,
                    geometry_identity_sha256=identity,
                    modelbin_entries=modelbin_entries,
                    modelbin_sha256=modelbin_hashes,
                    exported_archive=str(output / "archives" / archive.name),
                    copied_archive_sha256=copied_hash,
                    copy_verified=True,
                )
            )
            if len(exported) >= requested_limit:
                break

        unchanged = all(_sha256(path) == digest for path, digest in source_hashes_before.items())
        if not unchanged:
            raise TireFamilyExportError("one or more source tire archives changed during export")

        status = (
            "diagnostic_tire_family_export_ready"
            if exported
            else "diagnostic_tire_family_export_no_unique_nonexcluded_family"
        )
        manifest_path = output / "native_tire_family_samples_manifest.json"
        bundle_path = output / "native_tire_family_samples_bundle.zip"
        report = TireFamilyExportReport(
            source_tires_dir=str(source),
            output_dir=str(output),
            bundle_path=str(bundle_path),
            manifest_path=str(manifest_path),
            requested_limit=requested_limit,
            excluded_model_names=excluded,
            inspected_archive_count=inspected,
            exported_unique_geometry_count=len(exported),
            exported=tuple(exported),
            skipped_duplicate_geometry=tuple(duplicates),
            source_archives_read_only_unchanged=True,
            status=status,
            production_mapping_enabled=False,
            limitations=(
                "Exporting copies does not establish selector semantics or production suitability.",
                "Distinct TireModelName values with identical modelbin bytes count as one geometry family.",
                "The source FH6 tire library is read only; all output is written outside the game directory.",
                "Production tire assembly remains disabled.",
            ),
        )
        staging_manifest = staging / manifest_path.name
        staging_manifest.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        staging_bundle = staging / bundle_path.name
        with zipfile.ZipFile(staging_bundle, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(staging_manifest, staging_manifest.name)
            for item in exported:
                copied = archive_dir / Path(item.exported_archive).name
                bundle.write(copied, f"archives/{copied.name}")

        staging.replace(output)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def export_native_tire_family_samples(
    game_or_cars_path: str | Path,
    output_dir: str | Path,
    *,
    exclude_model_names: Iterable[str] = ("Slick",),
    limit: int = 5,
) -> TireFamilyExportReport:
    """Resolve the FH6 native tire directory, then export diagnostic family samples."""
    try:
        tires_dir = tire_library_dir(game_or_cars_path)
    except TireAssetError as exc:
        raise TireFamilyExportError(str(exc)) from exc
    return export_tire_family_samples_from_directory(
        tires_dir,
        output_dir,
        exclude_model_names=exclude_model_names,
        limit=limit,
    )
