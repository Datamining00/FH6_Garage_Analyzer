from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .tire_morph_formula_pipeline import (
    TireMorphFormulaValidationError,
    TireMorphFormulaValidationReport,
    validate_stock_tire_morph_formula,
)


class TireMorphCrossFamilyValidationError(RuntimeError):
    """Raised when cross-family tire validation cannot run without ambiguity."""


@dataclass(frozen=True)
class TireMorphCrossFamilyValidationReport:
    requested_car_ids: tuple[int, ...]
    reports: tuple[TireMorphFormulaValidationReport, ...]
    unique_tire_model_names: tuple[str, ...]
    min_unique_families: int
    unique_family_count: int
    enough_unique_families: bool
    formula_role_corroborated_car_ids: tuple[int, ...]
    stock_geometry_corroborated_car_ids: tuple[int, ...]
    all_formula_roles_corroborated: bool
    all_stock_geometry_corroborated: bool
    production_mapping_enabled: bool
    complete_mapping_status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_morph_cross_family_validation_v1",
            "requested_car_ids": list(self.requested_car_ids),
            "reports": [item.as_dict() for item in self.reports],
            "unique_tire_model_names": list(self.unique_tire_model_names),
            "min_unique_families": self.min_unique_families,
            "unique_family_count": self.unique_family_count,
            "enough_unique_families": self.enough_unique_families,
            "formula_role_corroborated_car_ids": list(
                self.formula_role_corroborated_car_ids
            ),
            "stock_geometry_corroborated_car_ids": list(
                self.stock_geometry_corroborated_car_ids
            ),
            "all_formula_roles_corroborated": self.all_formula_roles_corroborated,
            "all_stock_geometry_corroborated": self.all_stock_geometry_corroborated,
            "production_mapping_enabled": self.production_mapping_enabled,
            "complete_mapping_status": self.complete_mapping_status,
            "limitations": list(self.limitations),
        }


def _normalized_car_ids(car_ids: Sequence[int]) -> tuple[int, ...]:
    result = tuple(int(value) for value in car_ids)
    if not result:
        raise TireMorphCrossFamilyValidationError("at least one car_id is required")
    if any(value <= 0 for value in result):
        raise TireMorphCrossFamilyValidationError(
            f"all car_ids must be positive: {result!r}"
        )
    if len(set(result)) != len(result):
        raise TireMorphCrossFamilyValidationError(
            "duplicate car_ids are not valid cross-family evidence"
        )
    return result


def _formula_roles_corroborated(report: TireMorphFormulaValidationReport) -> bool:
    selectors = {
        int(item.selector): str(item.corroboration)
        for item in report.evidence.selector_evidence
    }
    return (
        selectors.get(0) == "geometry_corroborated"
        and selectors.get(1) == "geometry_corroborated"
        and report.evidence.width_scale_normalization_status
        == "base_x_normalization_consistent"
    )


def _unique_family_names(
    reports: Sequence[TireMorphFormulaValidationReport],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for report in reports:
        name = report.car_spec.tire_model_name
        if not name:
            raise TireMorphCrossFamilyValidationError(
                f"car {report.car_spec.car_id} has no TireModelName"
            )
        key = str(name).casefold()
        if key not in seen:
            seen.add(key)
            result.append(str(name))
    return tuple(result)


def validate_stock_tire_morph_families(
    game_or_cars_path: str | Path,
    database_path: str | Path,
    car_ids: Sequence[int],
    *,
    min_unique_families: int = 2,
) -> TireMorphCrossFamilyValidationReport:
    """Validate the diagnostic stock-tire mapping across multiple tire families.

    Each requested car is run through the complete read-only one-click validator.
    Cross-family corroboration requires at least ``min_unique_families`` distinct
    TireModelName values, selector 0/1 plus base-X normalization corroboration for
    every requested car, and stock width/outer-diameter corroboration for every
    requested car. Passing this report still does not enable production assembly.
    """
    ids = _normalized_car_ids(car_ids)
    minimum = int(min_unique_families)
    if minimum < 2:
        raise TireMorphCrossFamilyValidationError(
            "min_unique_families must be at least 2 for cross-family evidence"
        )
    if len(ids) < minimum:
        raise TireMorphCrossFamilyValidationError(
            f"at least {minimum} distinct car_ids are required; got {len(ids)}"
        )

    reports: list[TireMorphFormulaValidationReport] = []
    for car_id in ids:
        try:
            report = validate_stock_tire_morph_formula(
                game_or_cars_path,
                database_path,
                car_id,
            )
        except TireMorphFormulaValidationError as exc:
            raise TireMorphCrossFamilyValidationError(
                f"car {car_id} validation failed: {exc}"
            ) from exc
        reports.append(report)

    family_names = _unique_family_names(reports)
    enough_families = len(family_names) >= minimum
    formula_ids = tuple(
        int(report.car_spec.car_id)
        for report in reports
        if _formula_roles_corroborated(report)
    )
    geometry_ids = tuple(
        int(report.car_spec.car_id)
        for report in reports
        if report.stock_geometry.complete_mapping_status
        == "diagnostic_stock_dimensions_corroborated"
    )
    all_formula = len(formula_ids) == len(reports)
    all_geometry = len(geometry_ids) == len(reports)

    if not enough_families:
        status = "diagnostic_cross_family_insufficient_unique_families"
    elif all_formula and all_geometry:
        status = "diagnostic_cross_family_corroborated"
    else:
        status = "diagnostic_cross_family_not_corroborated"

    return TireMorphCrossFamilyValidationReport(
        requested_car_ids=ids,
        reports=tuple(reports),
        unique_tire_model_names=family_names,
        min_unique_families=minimum,
        unique_family_count=len(family_names),
        enough_unique_families=enough_families,
        formula_role_corroborated_car_ids=formula_ids,
        stock_geometry_corroborated_car_ids=geometry_ids,
        all_formula_roles_corroborated=all_formula,
        all_stock_geometry_corroborated=all_geometry,
        production_mapping_enabled=False,
        complete_mapping_status=status,
        limitations=(
            "Cross-family corroboration is limited to the explicitly requested stock vehicles and their resolved TireModelName archives.",
            "A passing result does not prove selectors 2..4 or vehicle spindle placement semantics.",
            "Production tire assembly remains disabled even when every requested family is corroborated.",
        ),
    )
