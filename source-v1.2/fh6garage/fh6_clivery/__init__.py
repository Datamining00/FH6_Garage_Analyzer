"""Independent, read-only FH6 C_livery/C_group decoding and M4 semantic boundary."""

from .container import CliveryDecodeError, ContainerInfo, inflate_clivery
from .decoder import (
    FORMAT_ID,
    SECTION_NAMES,
    CliveryMilestone1,
    CliveryScene,
    SectionCount,
    decode_clivery_bytes,
    decode_clivery_file,
    decode_clivery_file_to_json,
)
from .flatten import (
    M4_FORMAT_ID,
    EffectiveTransform,
    FlattenError,
    FlattenedLayer,
    FlattenedLivery,
    FlattenedSection,
    flatten_livery_scene,
)
from .livery_sections import (
    LiveryArtworkResult,
    LiverySectionDecodeError,
    LiverySectionResult,
    decode_livery_sections,
)
from .records import RawRecord, SourceSpan, Transform
from .scene import GroupNode, ShapeNode, UnknownNode
from .semantic_diff import (
    SemanticDifference,
    SemanticDiffReport,
    SemanticLayer,
    compare_semantic_layers,
    semantic_layers_from_flattened,
)

__all__ = [
    "CliveryDecodeError", "ContainerInfo", "inflate_clivery",
    "FORMAT_ID", "M4_FORMAT_ID", "SECTION_NAMES",
    "CliveryScene", "CliveryMilestone1", "SectionCount",
    "decode_clivery_bytes", "decode_clivery_file", "decode_clivery_file_to_json",
    "LiveryArtworkResult", "LiverySectionDecodeError", "LiverySectionResult",
    "decode_livery_sections",
    "RawRecord", "SourceSpan", "Transform", "GroupNode", "ShapeNode", "UnknownNode",
    "EffectiveTransform", "FlattenError", "FlattenedLayer", "FlattenedLivery",
    "FlattenedSection", "flatten_livery_scene",
    "SemanticLayer", "SemanticDifference", "SemanticDiffReport",
    "semantic_layers_from_flattened", "compare_semantic_layers",
]
