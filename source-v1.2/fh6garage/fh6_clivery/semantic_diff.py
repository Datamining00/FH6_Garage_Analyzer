from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .flatten import FlattenedLayer, FlattenedLivery


@dataclass(frozen=True)
class SemanticLayer:
    section: str
    order_index: int
    type_word: int
    parent_path: tuple[int, ...]
    source_offset: int | None
    transform: tuple[float, float, float, float, float, float]
    mask: bool | None
    color_rgba: tuple[int, int, int, int]


@dataclass(frozen=True)
class SemanticDifference:
    section: str
    order_index: int
    field: str
    ours: object
    oracle: object


@dataclass(frozen=True)
class SemanticDiffReport:
    ours_count: int
    oracle_count: int
    differences: tuple[SemanticDifference, ...]

    @property
    def match(self) -> bool:
        return self.ours_count == self.oracle_count and not self.differences

    def to_dict(self) -> dict[str, object]:
        return {
            "ours_count": self.ours_count,
            "oracle_count": self.oracle_count,
            "match": self.match,
            "differences": [
                {
                    "section": item.section,
                    "order_index": item.order_index,
                    "field": item.field,
                    "ours": item.ours,
                    "oracle": item.oracle,
                }
                for item in self.differences
            ],
        }


def semantic_layers_from_flattened(livery: FlattenedLivery) -> tuple[SemanticLayer, ...]:
    result: list[SemanticLayer] = []
    for section in livery.sections:
        for layer in section.layers:
            t = layer.transform
            result.append(
                SemanticLayer(
                    section=section.name,
                    order_index=layer.traversal_index,
                    type_word=layer.type_word,
                    parent_path=layer.source_parent_path,
                    source_offset=layer.source_offset,
                    transform=(t.x, t.y, t.sx, t.sy, t.rotation, t.skew),
                    mask=layer.mask,
                    color_rgba=layer.color_rgba,
                )
            )
    return tuple(result)


def compare_semantic_layers(
    ours: Iterable[SemanticLayer],
    oracle: Iterable[SemanticLayer],
    *,
    transform_abs_tol: float = 1e-6,
    compare_source_offset: bool = True,
) -> SemanticDiffReport:
    """Compare neutral semantic output, independent of any FLS implementation API.

    An FLS exporter can be normalized into `SemanticLayer` objects externally;
    this module intentionally contains no FLS runtime/import/implementation code.
    """
    ours_list = tuple(ours)
    oracle_list = tuple(oracle)
    differences: list[SemanticDifference] = []

    for index, (left, right) in enumerate(zip(ours_list, oracle_list)):
        section = left.section
        fields = (
            ("section", left.section, right.section),
            ("order_index", left.order_index, right.order_index),
            ("shape_identity", left.type_word, right.type_word),
            ("parent_path", left.parent_path, right.parent_path),
            ("mask", left.mask, right.mask),
            ("color", left.color_rgba, right.color_rgba),
        )
        for field, a, b in fields:
            if a != b:
                differences.append(SemanticDifference(section, index, field, a, b))
        if compare_source_offset and left.source_offset != right.source_offset:
            differences.append(
                SemanticDifference(section, index, "source_offset", left.source_offset, right.source_offset)
            )
        if len(left.transform) != len(right.transform) or any(
            not math.isclose(a, b, rel_tol=0.0, abs_tol=transform_abs_tol)
            for a, b in zip(left.transform, right.transform)
        ):
            differences.append(
                SemanticDifference(section, index, "transform", left.transform, right.transform)
            )

    if len(ours_list) != len(oracle_list):
        differences.append(
            SemanticDifference(
                "*",
                min(len(ours_list), len(oracle_list)),
                "leaf_count",
                len(ours_list),
                len(oracle_list),
            )
        )

    return SemanticDiffReport(len(ours_list), len(oracle_list), tuple(differences))
