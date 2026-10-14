from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable
import zipfile

from .tire_asset import TireAssetError, tire_library_dir
from .tire_family_export import (
    TireFamilyExportError,
    TireFamilyExportReport,
    export_tire_family_samples_from_directory,
)
from .tire_morph_signature_comparison import (
    CrossFamilySelectorSignatureReport,
    TireMorphSignatureComparisonError,
    compare_native_tire_selector_signatures,
)


class TireCrossFamilyDiagnosticError(RuntimeError):
    """Raised when the one-click native tire diagnostic cannot run safely."""


@dataclass(frozen=True)
class TireCrossFamilyDiagnosticReport:
    source_tires_dir: str
    output_dir: str
    reference_model_name: str
    reference_source_archive: str
    reference_source_sha256: str
    reference_copy: str
    reference_copy_sha256: str
    reference_copy_verified: bool
    family_export: TireFamilyExportReport
    signature_comparison: CrossFamilySelectorSignatureReport
    comparison_report_path: str
    manifest_path: str
    bundle_path: str
    source_archives_read_only_unchanged: bool
    status: str
    production_mapping_enabled: bool
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_cross_family_one_click_diagnostic_v1",
            "source_tires_dir": self.source_tires_dir,
            "output_dir": self.output_dir,
            "reference_model_name": self.reference_model_name,
            "reference_source_archive": self.reference_source_archive,
            "reference_source_sha256": self.reference_source_sha256,
            "reference_copy": self.reference_copy,
            "reference_copy_sha256": self.reference_copy_sha256,
            "reference_copy_verified": self.reference_copy_verified,
            "family_export": self.family_export.as_dict(),
            "signature_comparison": self.signature_comparison.as_dict(),
            "comparison_report_path": self.comparison_report_path,
            "manifest_path": self.manifest_path,
            "bundle_path": self.bundle_path,
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


def _resolve_reference_archive(tires_dir: Path, model_name: str) -> Path:
    normalized = str(model_name).strip()
    if not normalized:
        raise TireCrossFamilyDiagnosticError("reference_model_name must not be empty")
    wanted = f"tire_{normalized}.zip".casefold()
    try:
        matches = [
            path
            for path in tires_dir.iterdir()
            if path.is_file() and path.name.casefold() == wanted
        ]
    except (OSError, PermissionError) as exc:
        raise TireCrossFamilyDiagnosticError(
            f"could not inspect native tire library: {exc}"
        ) from exc
    if not matches:
        raise TireCrossFamilyDiagnosticError(
            f"reference native tire archive was not found: tire_{normalized}.zip"
        )
    if len(matches) != 1:
        raise TireCrossFamilyDiagnosticError(
            f"reference native tire archive is ambiguous: tire_{normalized}.zip"
        )
    return matches[0]


def _overall_status(comparison_status: str) -> str:
    mapping = {
        "diagnostic_cross_family_selector_signature_consistent": (
            "diagnostic_one_click_cross_family_signature_consistent"
        ),
        "diagnostic_cross_family_selector_signature_differs": (
            "diagnostic_one_click_cross_family_signature_differs"
        ),
        "diagnostic_selector_signature_insufficient_unique_families": (
            "diagnostic_one_click_insufficient_unique_families"
        ),
        "diagnostic_selector_signature_inconsistent_within_archive": (
            "diagnostic_one_click_signature_inconsistent_within_archive"
        ),
    }
    return mapping.get(comparison_status, "diagnostic_one_click_unclassified")


def run_native_tire_cross_family_diagnostic_from_directory(
    tires_dir: str | Path,
    output_dir: str | Path,
    *,
    reference_model_name: str = "Slick",
    exclude_model_names: Iterable[str] = (),
    candidate_limit: int = 5,
    quantitative_tolerance: float = 0.25,
    minimum_unique_geometry_families: int = 2,
) -> TireCrossFamilyDiagnosticReport:
    """Export unique native tire families and compare selector signatures in one run.

    The native FH6 tire library is never modified. The reference and candidate ZIPs
    are copied into a standalone diagnostic directory and all geometry analysis runs
    against those verified copies.
    """
    source = Path(tires_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise TireCrossFamilyDiagnosticError(f"native tire directory does not exist: {source}")
    if output.exists():
        raise TireCrossFamilyDiagnosticError(f"output directory already exists: {output}")
    if _is_within(output, source):
        raise TireCrossFamilyDiagnosticError(
            "output directory must be outside the native FH6 tire library"
        )
    limit = int(candidate_limit)
    if limit <= 0:
        raise TireCrossFamilyDiagnosticError("candidate_limit must be greater than zero")

    reference = _resolve_reference_archive(source, reference_model_name)
    reference_before = _sha256(reference)
    excluded = list(exclude_model_names)
    excluded.append(reference_model_name)

    try:
        export_dir = output / "family_export"
        family_export = export_tire_family_samples_from_directory(
            source,
            export_dir,
            exclude_model_names=excluded,
            limit=limit,
        )

        reference_dir = output / "reference"
        reference_dir.mkdir(parents=True, exist_ok=True)
        reference_copy = reference_dir / reference.name
        shutil.copyfile(reference, reference_copy)
        reference_copy_sha = _sha256(reference_copy)
        if reference_copy_sha != reference_before:
            raise TireCrossFamilyDiagnosticError("reference tire copy hash mismatch")
        if _sha256(reference) != reference_before:
            raise TireCrossFamilyDiagnosticError(
                "reference source archive changed during diagnostic copy"
            )

        candidate_copies = [Path(item.exported_archive) for item in family_export.exported]
        comparison_inputs = [reference_copy, *candidate_copies]
        try:
            comparison = compare_native_tire_selector_signatures(
                comparison_inputs,
                quantitative_tolerance=quantitative_tolerance,
                minimum_unique_geometry_families=minimum_unique_geometry_families,
            )
        except TireMorphSignatureComparisonError as exc:
            raise TireCrossFamilyDiagnosticError(str(exc)) from exc

        comparison_path = output / "native_tire_selector_signature_comparison.json"
        comparison_path.write_text(
            json.dumps(comparison.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        source_unchanged = (
            _sha256(reference) == reference_before
            and family_export.source_archives_read_only_unchanged
        )
        if not source_unchanged:
            raise TireCrossFamilyDiagnosticError(
                "one or more native source tire archives changed during analysis"
            )

        manifest_path = output / "native_tire_cross_family_diagnostic_manifest.json"
        bundle_path = output / "native_tire_cross_family_diagnostic_bundle.zip"
        report = TireCrossFamilyDiagnosticReport(
            source_tires_dir=str(source),
            output_dir=str(output),
            reference_model_name=str(reference_model_name).strip(),
            reference_source_archive=str(reference),
            reference_source_sha256=reference_before,
            reference_copy=str(reference_copy),
            reference_copy_sha256=reference_copy_sha,
            reference_copy_verified=True,
            family_export=family_export,
            signature_comparison=comparison,
            comparison_report_path=str(comparison_path),
            manifest_path=str(manifest_path),
            bundle_path=str(bundle_path),
            source_archives_read_only_unchanged=True,
            status=_overall_status(comparison.status),
            production_mapping_enabled=False,
            limitations=(
                "The one-click result is diagnostic evidence only and does not assign selector 2..4 semantics.",
                "Normalized signature tolerance is a comparison heuristic, not a production acceptance threshold.",
                "All compared ZIPs are verified copies; native FH6 source archives remain read only.",
                "Production tire assembly remains disabled regardless of result status.",
            ),
        )
        manifest_path.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(manifest_path, manifest_path.name)
            bundle.write(comparison_path, comparison_path.name)
            bundle.write(reference_copy, f"reference/{reference_copy.name}")
            export_manifest = Path(family_export.manifest_path)
            bundle.write(export_manifest, f"family_export/{export_manifest.name}")
            for item in family_export.exported:
                copied = Path(item.exported_archive)
                bundle.write(copied, f"family_export/archives/{copied.name}")

        return report
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def run_native_tire_cross_family_diagnostic(
    game_or_cars_path: str | Path,
    output_dir: str | Path,
    *,
    reference_model_name: str = "Slick",
    exclude_model_names: Iterable[str] = (),
    candidate_limit: int = 5,
    quantitative_tolerance: float = 0.25,
    minimum_unique_geometry_families: int = 2,
) -> TireCrossFamilyDiagnosticReport:
    """Resolve the FH6 native tire library and run the complete read-only diagnostic."""
    try:
        tires_dir = tire_library_dir(game_or_cars_path)
    except TireAssetError as exc:
        raise TireCrossFamilyDiagnosticError(str(exc)) from exc
    try:
        return run_native_tire_cross_family_diagnostic_from_directory(
            tires_dir,
            output_dir,
            reference_model_name=reference_model_name,
            exclude_model_names=exclude_model_names,
            candidate_limit=candidate_limit,
            quantitative_tolerance=quantitative_tolerance,
            minimum_unique_geometry_families=minimum_unique_geometry_families,
        )
    except TireFamilyExportError as exc:
        raise TireCrossFamilyDiagnosticError(str(exc)) from exc
