from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .carbin_structural import CarbinStructuralError, parse_fh6_carbin


TIRE_SPINDLE_ATTACHMENT_REVISION = "native_carbin_wheelstyle_spindle_contract_v3"
_WHEEL_STYLE_PART_TYPE = 44
_EXPECTED_SPINDLES: dict[str, tuple[str, str]] = {
    "spindleLF": ("front", "left"),
    "spindleRF": ("front", "right"),
    "spindleLR": ("rear", "left"),
    "spindleRR": ("rear", "right"),
}


class TireSpindleAttachmentError(RuntimeError):
    """Raised when a spindle attachment cannot be proven from native carbin evidence."""


@dataclass(frozen=True)
class TireSpindleAttachment:
    spindle_bone: str
    axle: str
    side: str
    carbin_resource_path: str
    carbin_transform_matrix_row_major: tuple[float, ...]
    derived_tire_entry: str
    derived_tire_glb_path: str
    derived_tire_source_side: str
    side_source_mode: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["carbin_transform_matrix_row_major"] = list(
            self.carbin_transform_matrix_row_major
        )
        return payload


@dataclass(frozen=True)
class TireSpindleAttachmentContract:
    status: str
    revision: str
    car_id: int
    attachment_part_type: int
    attachments: tuple[TireSpindleAttachment, ...]
    native_carbin_transform_only: bool
    procedural_translation_applied: bool
    procedural_rotation_applied: bool
    procedural_scale_applied: bool
    spindle_attachment_contract_ready: bool
    spindle_attachment_applied: bool
    production_renderer_enabled: bool
    limitations: tuple[str, ...]

    @property
    def tire_part_type(self) -> int:
        """Compatibility alias retained for the v1 diagnostic contract."""
        return self.attachment_part_type

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_spindle_attachment_contract_v2",
            "status": self.status,
            "revision": self.revision,
            "car_id": self.car_id,
            "attachment_part_type": self.attachment_part_type,
            "tire_part_type": self.attachment_part_type,
            "attachments": [item.as_dict() for item in self.attachments],
            "native_carbin_transform_only": self.native_carbin_transform_only,
            "procedural_translation_applied": self.procedural_translation_applied,
            "procedural_rotation_applied": self.procedural_rotation_applied,
            "procedural_scale_applied": self.procedural_scale_applied,
            "spindle_attachment_contract_ready": self.spindle_attachment_contract_ready,
            "spindle_attachment_applied": self.spindle_attachment_applied,
            "production_renderer_enabled": self.production_renderer_enabled,
            "limitations": list(self.limitations),
        }


def _finite_matrix(raw: object, *, bone: str) -> tuple[float, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise TireSpindleAttachmentError(
            f"{bone}: native carbin transform is not a 16-value sequence"
        )
    if len(raw) != 16:
        raise TireSpindleAttachmentError(
            f"{bone}: native carbin transform has {len(raw)} values; expected 16"
        )
    matrix = tuple(float(value) for value in raw)
    if not all(math.isfinite(value) for value in matrix):
        raise TireSpindleAttachmentError(
            f"{bone}: native carbin transform contains a non-finite value"
        )
    return matrix


def _stock_models_from_wheelstyle_part(part: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    if int(part.get("resolved_part_type", -1)) != _WHEEL_STYLE_PART_TYPE:
        return ()

    kind = str(part.get("kind") or "")
    if kind == "standard":
        models = part.get("models") or ()
        return tuple(model for model in models if isinstance(model, Mapping))

    if kind != "upgradable":
        return ()

    upgrades = [
        upgrade
        for upgrade in (part.get("upgrades") or ())
        if isinstance(upgrade, Mapping) and bool(upgrade.get("is_stock"))
    ]
    if len(upgrades) != 1:
        raise TireSpindleAttachmentError(
            "CCarParts_WheelStyle must have exactly one stock upgrade for the native tire preview"
        )
    stock = upgrades[0]
    stock_part_id = int(stock.get("part_id", -1))
    if stock_part_id < 0:
        raise TireSpindleAttachmentError(
            "stock CCarParts_WheelStyle upgrade has no valid part_id"
        )

    selected: list[Mapping[str, Any]] = []
    for model in stock.get("legacy_models") or ():
        if isinstance(model, Mapping):
            selected.append(model)
    for shared in part.get("shared_models") or ():
        if not isinstance(shared, Mapping):
            continue
        upgrade_ids = tuple(int(value) for value in (shared.get("upgrade_ids") or ()))
        model = shared.get("model")
        if stock_part_id in upgrade_ids and isinstance(model, Mapping):
            selected.append(model)
    return tuple(selected)


def _native_spindle_models(parsed_carbin: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    found: dict[str, list[Mapping[str, Any]]] = {name: [] for name in _EXPECTED_SPINDLES}
    rim_parts = parsed_carbin.get("rim_related_parts") or ()
    for part in rim_parts:
        if not isinstance(part, Mapping):
            continue
        if int(part.get("resolved_part_type", -1)) != _WHEEL_STYLE_PART_TYPE:
            continue
        for model in _stock_models_from_wheelstyle_part(part):
            bone = str(model.get("bone_name") or "")
            if bone in found:
                found[bone].append(model)

    missing = [bone for bone, models in found.items() if not models]
    duplicates = [bone for bone, models in found.items() if len(models) > 1]
    if missing:
        raise TireSpindleAttachmentError(
            "stock CCarParts_WheelStyle is missing exact native spindle bone(s): "
            + ", ".join(missing)
        )
    if duplicates:
        raise TireSpindleAttachmentError(
            "stock CCarParts_WheelStyle has ambiguous duplicate spindle bone(s): "
            + ", ".join(duplicates)
        )
    return {bone: models[0] for bone, models in found.items()}


def _entry_side(entry: str) -> str:
    stem = Path(str(entry).replace("\\", "/")).stem.casefold()
    if stem.startswith("tirel_"):
        return "left"
    if stem.startswith("tirer_"):
        return "right"
    raise TireSpindleAttachmentError(
        f"native tire modelbin entry does not expose an exact tireL_/tireR_ side identity: {entry!r}"
    )


def _trial_geometry_by_axle_side(
    trial_geometry: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    """Resolve front/rear tire derivatives to four vehicle sides.

    FH6 tire libraries use two native layouts observed in the actual files:
    (1) explicit tireL_ + tireR_ modelbins, and (2) a single tireL_ modelbin.
    Public ForzaTech extraction code likewise resolves the native tire asset through
    tireL_<TireModelName>.modelbin.  For layout (2), the same native derivative is
    therefore attached to both sides and the existing right-side WheelStyle spindle
    matrix supplies the native mirror/orientation.  No procedural geometry mirror,
    translation, rotation, or scale is introduced here.
    """
    if str(trial_geometry.get("format") or "") != "fh6_native_tire_production_trial_geometry_v1":
        raise TireSpindleAttachmentError("unsupported or missing production-trial geometry format")
    if str(trial_geometry.get("status") or "") != "production_trial_geometry_ready":
        raise TireSpindleAttachmentError("production-trial tire geometry is not ready")
    if not bool(trial_geometry.get("trial_renderer_input_ready")):
        raise TireSpindleAttachmentError("production-trial tire geometry is not renderer-input ready")
    if bool(trial_geometry.get("production_renderer_enabled")):
        raise TireSpindleAttachmentError(
            "production renderer was unexpectedly enabled before spindle contract validation"
        )

    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for axle in ("front", "rear"):
        axle_payload = trial_geometry.get(axle)
        if not isinstance(axle_payload, Mapping):
            raise TireSpindleAttachmentError(f"trial geometry is missing {axle} axle data")
        side_models: dict[str, Mapping[str, Any]] = {}
        for modelbin in axle_payload.get("modelbins") or ():
            if not isinstance(modelbin, Mapping):
                continue
            entry = str(modelbin.get("entry") or "")
            side = _entry_side(entry)
            if side in side_models:
                raise TireSpindleAttachmentError(
                    f"trial geometry has more than one {axle}/{side} native tire modelbin"
                )
            glb_path = str(modelbin.get("glb_path") or "")
            if not glb_path:
                raise TireSpindleAttachmentError(
                    f"trial geometry {axle}/{side} has no derived GLB path"
                )
            side_models[side] = modelbin

        if set(side_models) == {"left", "right"}:
            result[(axle, "left")] = side_models["left"]
            result[(axle, "right")] = side_models["right"]
            continue

        if set(side_models) == {"left"}:
            result[(axle, "left")] = side_models["left"]
            result[(axle, "right")] = side_models["left"]
            continue

        if set(side_models) == {"right"}:
            raise TireSpindleAttachmentError(
                f"trial geometry has only {axle}/right native tire modelbin; single-right reuse is not evidence-backed"
            )
        raise TireSpindleAttachmentError(
            f"trial geometry is missing native tire modelbin data for {axle} axle"
        )

    return result


def resolve_tire_spindle_attachment_contract(
    parsed_carbin: Mapping[str, Any],
    trial_geometry: Mapping[str, Any],
) -> TireSpindleAttachmentContract:
    """Resolve native tire attachments using only stock WheelStyle spindle transforms."""
    scene = parsed_carbin.get("scene")
    if not isinstance(scene, Mapping):
        raise TireSpindleAttachmentError("parsed carbin has no scene metadata")
    car_id = int(scene.get("ordinal", 0))
    trial_car_id = int(trial_geometry.get("car_id", 0))
    if car_id <= 0 or trial_car_id <= 0 or car_id != trial_car_id:
        raise TireSpindleAttachmentError(
            f"carbin/trial Car ID mismatch: carbin={car_id}, trial={trial_car_id}"
        )

    native_models = _native_spindle_models(parsed_carbin)
    trial_by_side = _trial_geometry_by_axle_side(trial_geometry)
    attachments: list[TireSpindleAttachment] = []
    for bone, (axle, side) in _EXPECTED_SPINDLES.items():
        model = native_models[bone]
        matrix = _finite_matrix(model.get("transform_matrix_row_major"), bone=bone)
        resource_path = str(model.get("resource_path") or "")
        if not resource_path:
            raise TireSpindleAttachmentError(
                f"{bone}: stock WheelStyle model has no native resource path"
            )
        derivative = trial_by_side[(axle, side)]
        entry = str(derivative.get("entry") or "").replace("\\", "/")
        source_side = _entry_side(entry)
        source_mode = (
            "exact_side_model"
            if source_side == side
            else "single_left_model_reused_by_native_spindle"
        )
        attachments.append(
            TireSpindleAttachment(
                spindle_bone=bone,
                axle=axle,
                side=side,
                carbin_resource_path=resource_path.replace("\\", "/"),
                carbin_transform_matrix_row_major=matrix,
                derived_tire_entry=entry,
                derived_tire_glb_path=str(derivative.get("glb_path") or ""),
                derived_tire_source_side=source_side,
                side_source_mode=source_mode,
            )
        )

    return TireSpindleAttachmentContract(
        status="spindle_attachment_contract_ready",
        revision=TIRE_SPINDLE_ATTACHMENT_REVISION,
        car_id=car_id,
        attachment_part_type=_WHEEL_STYLE_PART_TYPE,
        attachments=tuple(attachments),
        native_carbin_transform_only=True,
        procedural_translation_applied=False,
        procedural_rotation_applied=False,
        procedural_scale_applied=False,
        spindle_attachment_contract_ready=True,
        spindle_attachment_applied=False,
        production_renderer_enabled=False,
        limitations=(
            "Exact tireL_/tireR_ pairs are preserved when both native side models exist.",
            "A native tireL_-only family reuses that derivative on the right spindle because FH6/public extraction evidence uses tireL_ as the canonical single-model tire source; the native right WheelStyle matrix supplies side orientation.",
            "No procedural tire translation, rotation, scale, or geometry mirror is introduced.",
            "Brake-rotor, track-spacing, tire-spacer, and TireCompound placement formulas are not substituted for native WheelStyle transforms.",
        ),
    )


def build_tire_spindle_attachment_contract(
    carbin_data: bytes,
    trial_geometry: Mapping[str, Any],
    *,
    output_path: str | Path | None = None,
) -> TireSpindleAttachmentContract:
    try:
        parsed = parse_fh6_carbin(bytes(carbin_data))
    except CarbinStructuralError as exc:
        raise TireSpindleAttachmentError(f"could not parse FH6 carbin: {exc}") from exc
    contract = resolve_tire_spindle_attachment_contract(parsed, trial_geometry)
    if output_path is not None:
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(contract.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return contract
