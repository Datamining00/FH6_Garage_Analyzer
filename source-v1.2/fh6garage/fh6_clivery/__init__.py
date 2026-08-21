"""Independent, read-only FH6 C_livery/C_group decoding and M4 semantic boundary."""

from .container import CliveryDecodeError, ContainerInfo, inflate_clivery
from .cgroup import (
    CGROUP_FORMAT_ID,
    CGroupContainerInfo,
    CGroupDecodeError,
    CGroupScene,
    decode_cgroup_bytes,
    decode_cgroup_file,
    decode_cgroup_file_to_json,
    inflate_cgroup,
)
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
    "CGROUP_FORMAT_ID",
    "CGroupContainerInfo",
    "CGroupDecodeError",
    "CGroupScene",
    "CliveryDecodeError",
    "CliveryScene",
    "CliveryMilestone1",
    "ContainerInfo",
    "EffectiveTransform",
    "FlattenError",
    "FlattenedLayer",
    "FlattenedLivery",
    "FlattenedSection",
    "FORMAT_ID",
    "GroupNode",
    "LiveryArtworkResult",
    "LiverySectionDecodeError",
    "LiverySectionResult",
    "M4_FORMAT_ID",
    "RawRecord",
    "SECTION_NAMES",
    "SectionCount",
    "SemanticDifference",
    "SemanticDiffReport",
    "SemanticLayer",
    "ShapeNode",
    "SourceSpan",
    "Transform",
    "UnknownNode",
    "compare_semantic_layers",
    "decode_cgroup_bytes",
    "decode_cgroup_file",
    "decode_cgroup_file_to_json",
    "decode_clivery_bytes",
    "decode_clivery_file",
    "decode_clivery_file_to_json",
    "decode_livery_sections",
    "flatten_livery_scene",
    "inflate_cgroup",
    "inflate_clivery",
    "semantic_layers_from_flattened",
]
