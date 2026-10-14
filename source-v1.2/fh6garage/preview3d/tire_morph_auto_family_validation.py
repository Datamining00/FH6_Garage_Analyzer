from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .tire_family_candidates import (
    TireFamilyCandidateError,
    TireFamilyCandidateReport,
    select_stock_tire_family_candidates,
)
from .tire_morph_cross_family_validation import (
    TireMorphCrossFamilyValidationError,
    TireMorphCrossFamilyValidationReport,
    validate_stock_tire_morph_families,
)


class TireMorphAutoFamilyValidationError(RuntimeError):
    """Raised when automatic cross-family tire validation is ambiguous."""


@dataclass(frozen=True)
class TireMorphAutoFamilyValidationReport:
    candidate_selection: TireFamilyCandidateReport
    selected_car_ids: tuple[int, ...]
    selected_tire_model_names: tuple[str, ...]
    candidate_limit: int
    min_unique_families: int
    validation: TireMorphCrossFamilyValidationReport | None
    production_mapping_enabled: bool
    complete_mapping_status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_morph_auto_cross_family_validation_v1",
            "candidate_selection": self.candidate_selection.as_dict(),
            "selected_car_ids": list(self.selected_car_ids),
            "selected_tire_model_names": list(self.selected_tire_model_names),
            "candidate_limit": self.candidate_limit,
            "min_unique_families": self.min_unique_families,
            "validation": self.validation.as_dict() if self.validation is not None else None,
            "production_mapping_enabled": self.production_mapping_enabled,
            "complete_mapping_status": self.complete_mapping_status,
            "limitations": list(self.limitations),
        }


def validate_stock_tire_morph_families_auto(
    game_or_cars_path: str | Path,
    database_path: str | Path,
    *,
    exclude_model_names: Sequence[str] = (),
    candidate_limit: int = 3,
    min_unique_families: int = 2,
) -> TireMorphAutoFamilyValidationReport:
    """Select distinct stock tire families and validate them in one read-only pass.

    Candidate selection exact-matches DB ``TireModelName`` values to installed
    native tire archives. If fewer than ``min_unique_families`` resolvable stock
    families are available, the morph/geometry validator is not run. A completed
    validation remains diagnostic-only and never enables production assembly.
    """
    limit = int(candidate_limit)
    minimum = int(min_unique_families)
    if minimum < 2:
        raise TireMorphAutoFamilyValidationError(
            "min_unique_families must be at least 2"
        )
    if limit < minimum:
        raise TireMorphAutoFamilyValidationError(
            f"candidate_limit must be at least min_unique_families ({minimum}); got {limit}"
        )

    try:
        candidates = select_stock_tire_family_candidates(
            game_or_cars_path,
            database_path,
            exclude_model_names=exclude_model_names,
            limit=limit,
        )
    except TireFamilyCandidateError as exc:
        raise TireMorphAutoFamilyValidationError(str(exc)) from exc

    selected_ids = tuple(int(item.car_id) for item in candidates.candidates)
    selected_names = tuple(str(item.tire_model_name) for item in candidates.candidates)

    if len(selected_ids) < minimum:
        return TireMorphAutoFamilyValidationReport(
            candidate_selection=candidates,
            selected_car_ids=selected_ids,
            selected_tire_model_names=selected_names,
            candidate_limit=limit,
            min_unique_families=minimum,
            validation=None,
            production_mapping_enabled=False,
            complete_mapping_status="diagnostic_auto_cross_family_insufficient_candidates",
            limitations=(
                "Full morph/geometry validation was not run because too few distinct resolvable stock tire families were available.",
                "Only exact DB TireModelName-to-native-archive matches are eligible.",
                "Production tire assembly remains disabled.",
            ),
        )

    try:
        validation = validate_stock_tire_morph_families(
            game_or_cars_path,
            database_path,
            selected_ids,
            min_unique_families=minimum,
        )
    except TireMorphCrossFamilyValidationError as exc:
        raise TireMorphAutoFamilyValidationError(
            f"automatic cross-family validation failed: {exc}"
        ) from exc

    candidate_keys = {name.casefold() for name in selected_names}
    validation_keys = {name.casefold() for name in validation.unique_tire_model_names}
    if candidate_keys != validation_keys:
        raise TireMorphAutoFamilyValidationError(
            "candidate TireModelName set changed during validation: "
            f"selected={selected_names!r}, validated={validation.unique_tire_model_names!r}"
        )

    if validation.complete_mapping_status == "diagnostic_cross_family_corroborated":
        status = "diagnostic_auto_cross_family_corroborated"
    elif validation.complete_mapping_status == "diagnostic_cross_family_insufficient_unique_families":
        status = "diagnostic_auto_cross_family_insufficient_after_validation"
    else:
        status = "diagnostic_auto_cross_family_not_corroborated"

    return TireMorphAutoFamilyValidationReport(
        candidate_selection=candidates,
        selected_car_ids=selected_ids,
        selected_tire_model_names=selected_names,
        candidate_limit=limit,
        min_unique_families=minimum,
        validation=validation,
        production_mapping_enabled=False,
        complete_mapping_status=status,
        limitations=(
            "Automatic validation is limited to the selected representative stock car for each exact TireModelName family.",
            "A passing result does not establish selectors 2..4 or wheel-spindle placement semantics.",
            "Production tire assembly remains disabled even when all selected families are corroborated.",
        ),
    )
