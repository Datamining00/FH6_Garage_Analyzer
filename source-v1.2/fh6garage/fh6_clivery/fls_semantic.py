from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from .decoder import SECTION_NAMES
from .flatten import FlattenedLivery
from .fls_oracle import FLSProjectArtifact, load_fls_project_file
from .semantic_diff import (
    SemanticDiffReport,
    SemanticLayer,
    compare_semantic_layers,
    semantic_layers_from_flattened,
)


FLS_SEMANTIC_FORMAT_ID = "fh6-assistant-fls-semantic-v1"
FLS_CLIVERY_FLOAT32_ABS_TOL = 2e-5
_CONFORMAL_EPS = 1e-9


class FLSSemanticError(ValueError):
    """Raised when observed FLS project data cannot be normalized without guessing."""


@dataclass(frozen=True)
class FLSSemanticProject:
    raw_sha256: str
    uncompressed_sha256: str
    car_id: int
    section_counts: tuple[int, ...]
    layers: tuple[SemanticLayer, ...]
    evidence: str = "CORPUS_VALIDATED_FLS_PROJECT_V3_VECTOR_SCENE"

    def to_dict(self) -> dict[str, object]:
        return {
            "format": FLS_SEMANTIC_FORMAT_ID,
            "raw_sha256": self.raw_sha256,
            "uncompressed_sha256": self.uncompressed_sha256,
            "car_id": self.car_id,
            "section_counts": list(self.section_counts),
            "layer_count": len(self.layers),
            "evidence": self.evidence,
            "layers": [
                {
                    "section": layer.section,
                    "order_index": layer.order_index,
                    "shape_identity": layer.type_word,
                    "parent_path": list(layer.parent_path),
                    "source_offset": layer.source_offset,
                    "transform": list(layer.transform),
                    "mask": layer.mask,
                    "color": list(layer.color_rgba),
                }
                for layer in self.layers
            ],
        }


@dataclass(frozen=True)
class _Frame:
    x: float = 0.0
    y: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    rotation: float = 0.0

    @property
    def orientation(self) -> float:
        return 1.0 if self.sx * self.sy >= 0.0 else -1.0


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FLSSemanticError(f"FLS field {field!r} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise FLSSemanticError(f"FLS field {field!r} must be finite")
    return result


def _normalize_rotation(value: float) -> float:
    result = value % 360.0
    if abs(result - 360.0) < 1e-10 or abs(result) < 1e-12:
        return 0.0
    return result


def _transform_dict(value: object, *, group: bool) -> tuple[float, float, float, float, float, float]:
    if not isinstance(value, dict):
        raise FLSSemanticError("FLS scene transform must be an object")
    required = ("x", "y", "scale_x", "scale_y", "rotation", "skew")
    if any(key not in value for key in required):
        raise FLSSemanticError("FLS scene transform is missing an observed v3 transform field")
    x = _finite_number(value["x"], "transform.x")
    y = _finite_number(value["y"], "transform.y")
    sx = _finite_number(value["scale_x"], "transform.scale_x")
    sy = _finite_number(value["scale_y"], "transform.scale_y")
    rotation = _finite_number(value["rotation"], "transform.rotation")
    skew = _finite_number(value["skew"], "transform.skew")
    if sx == 0.0 or sy == 0.0:
        raise FLSSemanticError("FLS scene transform has zero scale")
    if group:
        if not math.isclose(skew, 0.0, rel_tol=0.0, abs_tol=1e-12):
            raise FLSSemanticError("FLS group skew is not yet validated against C_livery export")
        if not math.isclose(abs(sx), abs(sy), rel_tol=0.0, abs_tol=_CONFORMAL_EPS):
            raise FLSSemanticError("FLS non-conformal group scale is outside the current M4 evidence set")
    return x, y, sx, sy, rotation, skew


def _compose(parent: _Frame, transform: tuple[float, float, float, float, float, float]) -> _Frame:
    x, y, sx, sy, rotation, _skew = transform
    radians = math.radians(parent.rotation)
    cos_r = math.cos(radians)
    sin_r = math.sin(radians)
    dx = parent.sx * x
    dy = parent.sy * y
    return _Frame(
        x=parent.x + cos_r * dx - sin_r * dy,
        y=parent.y + sin_r * dx + cos_r * dy,
        sx=parent.sx * sx,
        sy=parent.sy * sy,
        rotation=_normalize_rotation(parent.rotation + parent.orientation * rotation),
    )


def _require_unit_opacity(node: dict[str, Any]) -> None:
    if "opacity" not in node:
        raise FLSSemanticError("FLS v3 scene node is missing observed opacity field")
    opacity = _finite_number(node["opacity"], "opacity")
    if not math.isclose(opacity, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise FLSSemanticError("FLS opacity other than 1.0 is not yet mapped to C_livery semantics")


def _color_rgba(value: object) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise FLSSemanticError("FLS vector shape color must be a four-element stored color list")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255:
            raise FLSSemanticError("FLS vector shape color components must be integers in [0,255]")
        result.append(item)
    # Controlled pair 5 plus the FLS canvas screenshot provides channel semantics:
    # stored [0,0,255,255] renders red and [255,0,0,255] renders blue. The v3
    # project list is therefore BGRA storage, matching the C_livery Shape bytes.
    b, g, r, a = result
    return r, g, b, a


def semantic_project_from_fls_artifact(artifact: FLSProjectArtifact) -> FLSSemanticProject:
    """Normalize only black-box FLS v3 fields observed in real exported test pairs.

    Controlled oracle pairs prove that FLS may recenter a group and rebake child
    local positions when exporting C_livery. Therefore this adapter compares effective
    leaf transforms after structural group composition, never raw local group frames.

    `visible` is deliberately not used: observed pairs contain `visible=false`
    vector leaves that are nevertheless serialized into C_livery unchanged.
    """
    document = artifact.document
    if document.get("format") != "fls_editor_project" or document.get("version") != 3:
        raise FLSSemanticError("only observed FLS editor project format/version 3 is mapped")
    if document.get("is_livery") is not True:
        raise FLSSemanticError("FLS semantic adapter requires a livery project")
    car_id = document.get("car_id")
    if isinstance(car_id, bool) or not isinstance(car_id, int):
        raise FLSSemanticError("FLS livery project car_id must be an integer")

    root = document.get("root")
    if not isinstance(root, dict) or not isinstance(root.get("children"), list):
        raise FLSSemanticError("FLS v3 root must contain the observed children list")

    sections: dict[int, dict[str, Any]] = {}
    for node in root["children"]:
        if not isinstance(node, dict):
            raise FLSSemanticError("FLS root child is not a scene object")
        if node.get("kind") != "group" or node.get("is_livery_section") is not True:
            raise FLSSemanticError("unmapped non-section root child is present in FLS livery project")
        slot = node.get("livery_section_slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < len(SECTION_NAMES):
            raise FLSSemanticError("FLS livery section has invalid observed slot")
        if slot in sections:
            raise FLSSemanticError(f"duplicate FLS livery section slot {slot}")
        if node.get("name") != SECTION_NAMES[slot]:
            raise FLSSemanticError(f"FLS section slot {slot} name does not match canonical section name")
        sections[slot] = node

    if set(sections) != set(range(len(SECTION_NAMES))):
        raise FLSSemanticError("FLS livery project does not contain exactly the eleven observed section groups")

    layers: list[SemanticLayer] = []
    section_counts: list[int] = []

    for slot, name in enumerate(SECTION_NAMES):
        section = sections[slot]
        _require_unit_opacity(section)
        section_frame = _compose(_Frame(), _transform_dict(section.get("transform"), group=True))
        section_layers: list[SemanticLayer] = []

        def walk(node: object, parent: _Frame, path: tuple[int, ...]) -> None:
            if not isinstance(node, dict):
                raise FLSSemanticError("FLS scene child is not an object")
            kind = node.get("kind")
            if kind == "group":
                _require_unit_opacity(node)
                frame = _compose(parent, _transform_dict(node.get("transform"), group=True))
                children = node.get("children")
                if not isinstance(children, list):
                    raise FLSSemanticError("FLS group children must be a list")
                for index, child in enumerate(children):
                    walk(child, frame, path + (index,))
                return
            if kind != "shape":
                raise FLSSemanticError(f"unsupported FLS scene node kind {kind!r}")

            _require_unit_opacity(node)
            visual = node.get("visual")
            if not isinstance(visual, dict) or visual.get("kind") != "vector":
                raise FLSSemanticError("only observed FLS vector shapes are mapped in M4c")
            shape_id = visual.get("shape_id")
            if isinstance(shape_id, bool) or not isinstance(shape_id, int) or not 0 <= shape_id <= 0xFFFF:
                raise FLSSemanticError("FLS vector shape_id must be a u16 integer")
            mask = node.get("mask")
            if not isinstance(mask, bool):
                raise FLSSemanticError("FLS vector shape mask must be boolean")

            transform = _transform_dict(node.get("transform"), group=False)
            frame = _compose(parent, transform)
            sx, sy, rotation = frame.sx, frame.sy, frame.rotation
            if sy < 0.0:
                sx = -sx
                sy = -sy
                rotation = _normalize_rotation(rotation + 180.0)
            skew = transform[5] * parent.orientation
            section_layers.append(
                SemanticLayer(
                    section=name,
                    order_index=len(section_layers),
                    type_word=shape_id,
                    parent_path=path,
                    source_offset=None,
                    transform=(frame.x, frame.y, sx, sy, rotation, skew),
                    mask=mask,
                    color_rgba=_color_rgba(node.get("color")),
                )
            )

        children = section.get("children")
        if not isinstance(children, list):
            raise FLSSemanticError("FLS livery section children must be a list")
        for index, child in enumerate(children):
            walk(child, section_frame, (slot, index))
        section_counts.append(len(section_layers))
        layers.extend(section_layers)

    return FLSSemanticProject(
        artifact.raw_sha256,
        artifact.uncompressed_sha256,
        car_id,
        tuple(section_counts),
        tuple(layers),
    )


def semantic_project_from_fls_file(path: str | Path) -> FLSSemanticProject:
    return semantic_project_from_fls_artifact(load_fls_project_file(path))


def compare_fls_project_to_flattened(
    oracle: FLSSemanticProject,
    ours: FlattenedLivery,
    *,
    transform_abs_tol: float = FLS_CLIVERY_FLOAT32_ABS_TOL,
) -> SemanticDiffReport:
    if oracle.car_id != ours.car_id:
        raise FLSSemanticError(f"FLS/C_livery car_id mismatch: {oracle.car_id} != {ours.car_id}")
    ours_counts = tuple(section.flattened_count for section in ours.sections)
    if oracle.section_counts != ours_counts:
        raise FLSSemanticError(
            f"FLS/C_livery section-count mismatch: {oracle.section_counts!r} != {ours_counts!r}"
        )
    return compare_semantic_layers(
        semantic_layers_from_flattened(ours),
        oracle.layers,
        transform_abs_tol=transform_abs_tol,
        compare_source_offset=False,
    )
