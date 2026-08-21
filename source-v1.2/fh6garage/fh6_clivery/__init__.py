"""Independent, read-only FH6 C_livery and C_group decoding boundary."""

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
    CliveryScene,
    CliveryMilestone1,
    SectionCount,
    decode_clivery_bytes,
    decode_clivery_file,
    decode_clivery_file_to_json,
)
from .livery_sections import (
    LiveryArtworkResult,
    LiverySectionDecodeError,
    LiverySectionResult,
    decode_livery_sections,
)
from .records import RawRecord, SourceSpan, Transform
from .scene import GroupNode, ShapeNode, UnknownNode

__all__ = [
    "CGROUP_FORMAT_ID",
    "CGroupContainerInfo",
    "CGroupDecodeError",
    "CGroupScene",
    "CliveryDecodeError",
    "CliveryScene",
    "CliveryMilestone1",
    "ContainerInfo",
    "FORMAT_ID",
    "GroupNode",
    "LiveryArtworkResult",
    "LiverySectionDecodeError",
    "LiverySectionResult",
    "RawRecord",
    "SECTION_NAMES",
    "SectionCount",
    "ShapeNode",
    "SourceSpan",
    "Transform",
    "UnknownNode",
    "decode_cgroup_bytes",
    "decode_cgroup_file",
    "decode_cgroup_file_to_json",
    "decode_clivery_bytes",
    "decode_clivery_file",
    "decode_clivery_file_to_json",
    "decode_livery_sections",
    "inflate_cgroup",
    "inflate_clivery",
]
