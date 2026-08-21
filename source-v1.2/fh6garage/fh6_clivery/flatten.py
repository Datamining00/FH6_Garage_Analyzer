from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .decoder import CliveryScene
from .scene import GroupNode, ShapeNode, UnknownNode


M4_FORMAT_ID = "fh6-assistant-independent-render-layers-m4"
RENDER_TYPE_BASE = 0x100000
_CONFORMAL_EPS = 1e-6


@dataclass(frozen=True)
class EffectiveTransform:
    x: float
    y: float
    sx: float
    sy: float
    rotation: float
    skew: float

    def to_list(self, *, mask: bool) -> list[float]:
        return [
            self.x,
            self.y,
            self.sx,
            self.sy,
            self.rotation,
            self.skew,
            1.0 if mask else 0.0,
        ]

    def to_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "sx": self.sx,
            "sy": self.sy,
            "rotation": self.rotation,
            "skew": self.skew,
        }


@dataclass(frozen=True)
class FlattenedLayer:
    type_word: int
    transform: EffectiveTransform
    color_rgba: tuple[int, int, int, int]
    mask: bool
    source_offset: int
    source_marker: str
    source_section: str
    source_parent_path: tuple[int, ...]
    mask_evidence: tuple[str, ...]
    traversal_index: int
    transform_evidence: str

    @property
    def type(self) -> int:
        return RENDER_TYPE_BASE + self.type_word

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "type_word": self.type_word,
            "type_word_hex": f"0x{self.type_word:04x}",
            "data": self.transform.to_list(mask=self.mask),
            "color": list(self.color_rgba),
            "mask": self.mask,
            "source_format": "fh6_independent_clivery",
            "source_offset": self.source_offset,
            "source_marker": self.source_marker,
            "source_section": self.source_section,
            "source_parent_path": list(self.source_parent_path),
            "mask_evidence": list(self.mask_evidence),
            "traversal_index": self.traversal_index,
            "transform_evidence": self.transform_evidence,
        }


@dataclass(frozen=True)
class FlattenedSection:
    slot: int
    name: str
    declared_count: int
    layers: tuple[FlattenedLayer, ...]
    complete: bool

    @property
    def flattened_count(self) -> int:
        return len(self.layers)

    @property
    def first_source_offset(self) -> int | None:
        return self.layers[0].source_offset if self.layers else None

    @property
    def last_source_offset(self) -> int | None:
        return self.layers[-1].source_offset if self.layers else None

    @property
    def mask_source_offsets(self) -> tuple[int, ...]:
        return tuple(layer.source_offset for layer in self.layers if layer.mask)

    def to_dict(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "declared_count": self.declared_count,
            "flattened_count": self.flattened_count,
            "first_source_offset": self.first_source_offset,
            "last_source_offset": self.last_source_offset,
            "mask_source_offsets": list(self.mask_source_offsets),
            "complete": self.complete,
            "layers": [layer.to_dict() for layer in self.layers],
        }


@dataclass(frozen=True)
class FlattenedLivery:
    car_id: int
    body_start: int
    body_end: int
    sections: tuple[FlattenedSection, ...]
    order_semantics: str = "STRUCTURAL_DEPTH_FIRST_CHILD_ORDER"
    draw_order_evidence: str = "PROVISIONAL_NOT_RENDERER_BOUND"

    def to_dict(self) -> dict[str, object]:
        return {
            "format": M4_FORMAT_ID,
            "car_id": self.car_id,
            "body_start": self.body_start,
            "body_end": self.body_end,
            "order_semantics": self.order_semantics,
            "draw_order_evidence": self.draw_order_evidence,
            "sections": {section.name: section.to_dict() for section in self.sections},
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


class FlattenError(ValueError):
    pass


def _normalize_rotation(value: float) -> float:
    result = value % 360.0
    if abs(result - 360.0) < 1e-10 or abs(result) < 1e-12:
        return 0.0
    return result


def _is_conformal_group(group: GroupNode) -> bool:
    return math.isclose(abs(group.transform.sx), abs(group.transform.sy), rel_tol=0.0, abs_tol=_CONFORMAL_EPS)


def _compose(parent: _Frame, *, x: float, y: float, sx: float, sy: float, rotation: float) -> _Frame:
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


def _compose_group(parent: _Frame, group: GroupNode) -> _Frame:
    if not _is_conformal_group(group):
        raise FlattenError(
            "Milestone 4 transform flattening only promotes conformal FH6 group frames; "
            f"group {group.parent_path} has sx={group.transform.sx!r}, sy={group.transform.sy!r}"
        )
    t = group.transform
    return _compose(parent, x=t.x, y=t.y, sx=t.sx, sy=t.sy, rotation=t.rotation)


def _compose_shape(parent: _Frame, shape: ShapeNode) -> EffectiveTransform:
    t = shape.transform
    frame = _compose(parent, x=t.x, y=t.y, sx=t.sx, sy=t.sy, rotation=t.rotation)
    skew = t.skew * parent.orientation
    # Renderer-facing canonical representation keeps Y scale non-negative. This
    # changes only the parameterization of the same reflected frame; it does not
    # reorder or otherwise mutate the scene tree.
    sx = frame.sx
    sy = frame.sy
    rotation = frame.rotation
    if sy < 0.0:
        sx = -sx
        sy = -sy
        rotation = _normalize_rotation(rotation + 180.0)
    return EffectiveTransform(frame.x, frame.y, sx, sy, rotation, skew)


def _resolve_masks(
    root: GroupNode,
    *,
    terminal_state: int = 0,
) -> dict[int, tuple[bool, tuple[str, ...]]]:
    """Resolve only mask semantics supported by current M4 corpus evidence.

    `0x60` ancestry is authoritative. Outside such ancestry, a direct Shape child
    with physical lead `01 02` carries trailing state for the immediately
    preceding direct Shape sibling. Controlled pair 5 proves this direct-sibling
    rule is independent of the preceding Shape's color.

    A populated section can carry the same one-bit state in the first byte of its
    post-tree remnant (or the one-byte terminal state for the last populated
    section); controlled FLS exports prove that state `1` masks the terminal direct
    Shape for both achromatic and chromatic colors. Group-terminal state remains
    unsupported and fails closed.
    """

    result: dict[int, tuple[bool, tuple[str, ...]]] = {}

    def walk(group: GroupNode, inherited_authoritative_mask: bool) -> None:
        authoritative = inherited_authoritative_mask or (
            group.mask and group.mask_evidence == "CONFIRMED_GROUP_60_ANCESTRY"
        )

        for child in group.children:
            if isinstance(child, ShapeNode):
                if authoritative:
                    result[id(child)] = (True, ("CONFIRMED_GROUP_60_ANCESTRY",))
                else:
                    result[id(child)] = (False, ("NO_EFFECTIVE_MASK",))
            elif isinstance(child, GroupNode):
                walk(child, authoritative)

        if authoritative:
            return

        for index, child in enumerate(group.children):
            if not isinstance(child, ShapeNode) or child.marker_hex.lower() != "0102" or index == 0:
                continue
            previous = group.children[index - 1]
            if not isinstance(previous, ShapeNode):
                # A state crossing a completed Group boundary is still unresolved.
                # Preserve the structure but do not guess a target leaf.
                continue
            result[id(previous)] = (True, ("shape_0102_trailing_state",))

    walk(root, False)

    if terminal_state not in (0, 1):
        raise FlattenError(f"unsupported livery section terminal state {terminal_state!r}")
    if terminal_state == 1:
        if not root.children:
            raise FlattenError("nonzero livery section terminal state has no target child")
        target = root.children[-1]
        if not isinstance(target, ShapeNode):
            raise FlattenError(
                "nonzero livery section terminal state after a Group is not yet semantically mapped"
            )
        current_mask, current_evidence = result.get(id(target), (False, ("NO_EFFECTIVE_MASK",)))
        if current_mask:
            result[id(target)] = (True, current_evidence + ("section_terminal_state_01",))
        else:
            result[id(target)] = (True, ("section_terminal_state_01",))

    return result


def _flatten_section(
    slot: int,
    name: str,
    declared_count: int,
    root: GroupNode | None,
    complete: bool,
    *,
    terminal_state: int = 0,
) -> FlattenedSection:
    if root is None:
        return FlattenedSection(slot, name, declared_count, (), complete)

    mask_map = _resolve_masks(root, terminal_state=terminal_state)
    layers: list[FlattenedLayer] = []

    def walk(group: GroupNode, parent_frame: _Frame) -> None:
        group_frame = _compose_group(parent_frame, group)
        for child in group.children:
            if isinstance(child, GroupNode):
                walk(child, group_frame)
            elif isinstance(child, ShapeNode):
                mask, evidence = mask_map.get(id(child), (False, ("NO_EFFECTIVE_MASK",)))
                layers.append(
                    FlattenedLayer(
                        type_word=child.shape_id,
                        transform=_compose_shape(group_frame, child),
                        color_rgba=child.color_rgba,
                        mask=mask,
                        source_offset=child.source_span.offset,
                        source_marker=child.marker_hex,
                        source_section=name,
                        source_parent_path=child.parent_path,
                        mask_evidence=evidence,
                        traversal_index=len(layers),
                        transform_evidence="CONFIRMED_CURRENT_CORPUS_CONFORMAL_GROUP_COMPOSITION",
                    )
                )
            elif isinstance(child, UnknownNode):
                raise FlattenError(
                    f"section {name} contains unresolved node at 0x{child.source_span.offset:x}; "
                    "Milestone 4 refuses to flatten unknown data"
                )

    walk(root, _Frame())
    if complete and len(layers) != declared_count:
        raise FlattenError(
            f"section {name} declared {declared_count} leaves but structural flatten produced {len(layers)}"
        )
    return FlattenedSection(slot, name, declared_count, tuple(layers), complete)


def flatten_livery_scene(scene: CliveryScene, section_names: Iterable[str] | None = None) -> FlattenedLivery:
    if scene.artwork is None:
        raise FlattenError("C_livery scene has no Milestone 3 artwork tree")

    requested = set(section_names) if section_names is not None else None
    terminal_state_by_tree_end: dict[int, int] = {}
    for record in scene.artwork.records:
        if record.kind not in {"livery_section_remnant", "livery_section_terminal_state"}:
            continue
        if not record.raw:
            raise FlattenError(f"{record.kind} at 0x{record.span.offset:x} is empty")
        terminal_state_by_tree_end[record.span.offset] = record.raw[0]

    output: list[FlattenedSection] = []
    for section in scene.artwork.sections:
        if requested is not None and section.name not in requested:
            continue
        output.append(
            _flatten_section(
                section.slot,
                section.name,
                section.declared_count,
                section.root,
                section.complete,
                terminal_state=terminal_state_by_tree_end.get(section.tree_end, 0),
            )
        )
    return FlattenedLivery(scene.car_id, scene.body_start, scene.body_end, tuple(output))
