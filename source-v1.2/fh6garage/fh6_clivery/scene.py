from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from .records import RawRecord, SourceSpan, Transform


@dataclass
class UnknownNode:
    source_span: SourceSpan
    raw_record: RawRecord
    reason: str
    parent_path: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "unknown",
            "source_span": self.source_span.to_dict(),
            "reason": self.reason,
            "parent_path": list(self.parent_path),
            "raw_record": self.raw_record.to_dict(),
        }


@dataclass
class ShapeNode:
    source_span: SourceSpan
    raw_record: RawRecord
    shape_id: int
    transform: Transform
    color_rgba: tuple[int, int, int, int]
    marker_hex: str
    mask: bool | None
    mask_evidence: str
    parent_path: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "shape",
            "source_span": self.source_span.to_dict(),
            "shape_id": self.shape_id,
            "transform": self.transform.to_dict(),
            "color_rgba": list(self.color_rgba),
            "marker_hex": self.marker_hex,
            "mask": self.mask,
            "mask_evidence": self.mask_evidence,
            "parent_path": list(self.parent_path),
            "raw_record": self.raw_record.to_dict(),
        }


SceneNode: TypeAlias = "GroupNode | ShapeNode | UnknownNode"


@dataclass
class GroupNode:
    header_span: SourceSpan
    source_span: SourceSpan
    raw_header: RawRecord
    marker_hex: str
    expected_direct_children: int
    child_bitmap: bytes
    transform: Transform
    mask: bool
    mask_evidence: str
    parent_path: tuple[int, ...]
    children: list[SceneNode] = field(default_factory=list)
    control_records: list[RawRecord] = field(default_factory=list)
    complete: bool = False

    @property
    def parsed_direct_children(self) -> int:
        return len(self.children)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "group",
            "header_span": self.header_span.to_dict(),
            "source_span": self.source_span.to_dict(),
            "marker_hex": self.marker_hex,
            "expected_direct_children": self.expected_direct_children,
            "parsed_direct_children": self.parsed_direct_children,
            "child_bitmap_hex": self.child_bitmap.hex(),
            "transform": self.transform.to_dict(),
            "mask": self.mask,
            "mask_evidence": self.mask_evidence,
            "parent_path": list(self.parent_path),
            "complete": self.complete,
            "control_records": [record.to_dict() for record in self.control_records],
            "children": [child.to_dict() for child in self.children],
        }


def tree_stats(root: GroupNode) -> dict[str, int | bool]:
    group_count = 0
    shape_count = 0
    unknown_count = 0
    max_depth = 0

    def walk(group: GroupNode, depth: int) -> None:
        nonlocal group_count, shape_count, unknown_count, max_depth
        max_depth = max(max_depth, depth)
        for child in group.children:
            if isinstance(child, GroupNode):
                group_count += 1
                walk(child, depth + 1)
            elif isinstance(child, ShapeNode):
                shape_count += 1
            else:
                unknown_count += 1

    walk(root, 0)
    return {
        "nested_group_count": group_count,
        "leaf_count": shape_count,
        "unknown_node_count": unknown_count,
        "max_group_depth": max_depth,
        "root_complete": root.complete,
    }
