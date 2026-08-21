from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

from .diagnostics import Diagnostic
from .records import RawRecord, SourceSpan, Transform
from .scene import GroupNode, ShapeNode, UnknownNode, tree_stats


CGROUP_FORMAT_ID = "fh6-assistant-cgroup-scene-v1"


class CGroupDecodeError(ValueError):
    """Raised when a standalone C_group cannot be framed safely."""


@dataclass(frozen=True)
class CGroupContainerInfo:
    source_kind: str
    raw_length: int
    payload_offset: int
    compressed_length: int | None
    declared_uncompressed_length: int | None
    actual_uncompressed_length: int

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "source_kind": self.source_kind,
            "raw_length": self.raw_length,
            "payload_offset": self.payload_offset,
            "compressed_length": self.compressed_length,
            "declared_uncompressed_length": self.declared_uncompressed_length,
            "actual_uncompressed_length": self.actual_uncompressed_length,
        }


@dataclass
class CGroupScene:
    container: CGroupContainerInfo
    version: int
    generation: int | None
    root: GroupNode
    records: tuple[RawRecord, ...]
    diagnostics: tuple[Diagnostic, ...]
    payload_length: int
    payload_sha256: str
    lossless_record_coverage: bool

    def to_dict(self) -> dict[str, object]:
        stats = tree_stats(self.root)
        stats["lossless_record_coverage"] = self.lossless_record_coverage
        return {
            "format": CGROUP_FORMAT_ID,
            "container": self.container.to_dict(),
            "version": self.version,
            "generation": self.generation,
            "payload_length": self.payload_length,
            "payload_sha256": self.payload_sha256,
            "stats": stats,
            "root": self.root.to_dict(),
            "records": [record.to_dict() for record in self.records],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise CGroupDecodeError(f"u16 at 0x{offset:x} is truncated")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise CGroupDecodeError(f"u32 at 0x{offset:x} is truncated")
    return struct.unpack_from("<I", data, offset)[0]


def _f32(data: bytes, offset: int) -> float:
    if offset < 0 or offset + 4 > len(data):
        raise CGroupDecodeError(f"f32 at 0x{offset:x} is truncated")
    return struct.unpack_from("<f", data, offset)[0]


def inflate_cgroup(raw: bytes | bytearray | memoryview) -> tuple[bytes, CGroupContainerInfo]:
    data = bytes(raw)
    if data.startswith(b"gyvl"):
        return data, CGroupContainerInfo(
            source_kind="inflated-payload",
            raw_length=len(data),
            payload_offset=0,
            compressed_length=None,
            declared_uncompressed_length=None,
            actual_uncompressed_length=len(data),
        )

    if len(data) < 8:
        raise CGroupDecodeError("C_group is too short for the 8-byte Forza container header")

    compressed_length, declared_uncompressed_length = struct.unpack_from("<II", data, 0)
    if compressed_length <= 0:
        raise CGroupDecodeError("C_group declares an empty compressed payload")
    if 8 + compressed_length != len(data):
        raise CGroupDecodeError(
            "C_group compressed length does not match file size "
            f"({compressed_length} compressed bytes, {len(data) - 8} available)"
        )

    try:
        payload = zlib.decompress(data[8:])
    except zlib.error as exc:
        raise CGroupDecodeError(f"C_group zlib payload could not be decompressed: {exc}") from exc

    if len(payload) != declared_uncompressed_length:
        raise CGroupDecodeError(
            "C_group decompressed length does not match header "
            f"({declared_uncompressed_length} declared, {len(payload)} actual)"
        )
    if not payload.startswith(b"gyvl"):
        raise CGroupDecodeError("decompressed C_group payload does not begin with 'gyvl'")

    return payload, CGroupContainerInfo(
        source_kind="fh6-cgroup-zlib-container",
        raw_length=len(data),
        payload_offset=8,
        compressed_length=compressed_length,
        declared_uncompressed_length=declared_uncompressed_length,
        actual_uncompressed_length=len(payload),
    )


def _child_is_group(bitmap: bytes, index: int) -> bool:
    byte_index = index // 8
    if byte_index >= len(bitmap):
        raise CGroupDecodeError("group child bitmap ended before declared child count")
    return bool(bitmap[byte_index] & (1 << (index % 8)))


def _transform_marker(data: bytes, pos: int) -> bytes | None:
    if pos >= len(data):
        return None

    for marker in (b"\xdf\x03\x03", b"\x03\x03", b"\x01\x03", b"\x03"):
        if data[pos:pos + len(marker)] == marker:
            return marker

    if data[pos] == 0x00:
        cursor = pos + 1
        while cursor < len(data) and data[cursor] == 0x01:
            cursor += 1
        if cursor < len(data) and data[cursor] == 0x03:
            return data[pos:cursor + 1]
    return None


def _try_transform(data: bytes, pos: int) -> tuple[Transform, int, bytes] | None:
    marker = _transform_marker(data, pos)
    if marker is None:
        return None

    payload_pos = pos + len(marker)
    if payload_pos + 16 > len(data):
        return None
    x, y, sx, rotation = struct.unpack_from("<ffff", data, payload_pos)
    if not all(math.isfinite(value) for value in (x, y, sx, rotation)) or sx == 0.0:
        return None

    sy = sx
    size = len(marker) + 16
    extension_pos = pos + size
    if extension_pos + 5 <= len(data) and data[extension_pos] == 0x30:
        sy = _f32(data, extension_pos + 1)
        if not math.isfinite(sy) or sy == 0.0:
            return None
        size += 5

    return (
        Transform(
            x=x,
            y=y,
            sx=sx,
            sy=sy,
            rotation=rotation,
            source_span=SourceSpan(pos, size),
        ),
        size,
        marker,
    )


def _try_shape(data: bytes, pos: int) -> tuple[dict[str, object], int] | None:
    if data[pos:pos + 2] in (b"\x00\x02", b"\x01\x02"):
        marker = data[pos:pos + 2]
        prefix = 2
        size = 32
    elif data[pos:pos + 1] == b"\x02":
        marker = b"\x02"
        prefix = 1
        size = 31
    else:
        return None

    if pos + size > len(data):
        return None

    shape_id = _u16(data, pos + prefix)
    rotation, x, y, sx, sy, skew = struct.unpack_from("<ffffff", data, pos + prefix + 2)
    if not all(math.isfinite(value) for value in (rotation, x, y, sx, sy, skew)):
        return None
    if sx == 0.0 or sy == 0.0:
        return None

    color_pos = pos + prefix + 26
    b, g, r, a = data[color_pos:color_pos + 4]
    return {
        "shape_id": shape_id,
        "marker": marker,
        "rotation": rotation,
        "x": x,
        "y": y,
        "sx": sx,
        "sy": sy,
        "skew": skew,
        "color_rgba": (r, g, b, a),
    }, size


def _try_counted_group(data: bytes, pos: int) -> tuple[int, bytes, int, int] | None:
    if pos + 7 > len(data) or data[pos] not in (0x20, 0x60):
        return None

    count = _u16(data, pos + 1)
    blocks = _u16(data, pos + 3)
    if blocks != (count + 7) // 8:
        return None

    size = 7 + blocks
    if pos + size > len(data):
        return None
    return count, data[pos + 7:pos + size], size, data[pos]


def _try_markerless_group(data: bytes, pos: int) -> tuple[int, bytes, int] | None:
    if pos + 6 > len(data):
        return None

    count = _u16(data, pos)
    blocks = _u16(data, pos + 2)
    if blocks != (count + 7) // 8:
        return None

    size = 6 + blocks
    if pos + size > len(data):
        return None
    return count, data[pos + 6:pos + size], size


class _Parser:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.records: list[RawRecord] = []
        self.diagnostics: list[Diagnostic] = []
        self.halted = False

    def add_record(
        self,
        kind: str,
        offset: int,
        length: int,
        evidence_state: str,
        marker: bytes | None = None,
    ) -> RawRecord:
        record = RawRecord(
            kind=kind,
            span=SourceSpan(offset, length),
            raw=self.payload[offset:offset + length],
            evidence_state=evidence_state,
            marker_hex=marker.hex() if marker else None,
        )
        self.records.append(record)
        return record

    def unknown_tail(
        self,
        pos: int,
        path: tuple[int, ...],
        reason: str,
    ) -> UnknownNode:
        record = self.add_record("unknown_span", pos, len(self.payload) - pos, "UNKNOWN")
        self.diagnostics.append(
            Diagnostic(
                severity="warning",
                code="CGROUP_UNKNOWN_TAIL",
                message=reason + "; no byte-by-byte recovery scan was attempted",
                offset=pos,
                evidence_state="UNKNOWN",
            )
        )
        self.halted = True
        return UnknownNode(
            source_span=record.span,
            raw_record=record,
            reason=reason,
            parent_path=path,
        )

    def make_group(
        self,
        *,
        header_pos: int,
        header_size: int,
        marker: int | None,
        count: int,
        bitmap: bytes,
        transform: Transform,
        inherited_mask: bool,
        path: tuple[int, ...],
        kind: str,
    ) -> GroupNode:
        marker_bytes = bytes([marker]) if marker is not None else None
        record = self.add_record(kind, header_pos, header_size, "CONFIRMED", marker_bytes)
        explicit_mask = marker == 0x60
        return GroupNode(
            header_span=record.span,
            source_span=record.span,
            raw_header=record,
            marker_hex=marker_bytes.hex() if marker_bytes else "",
            expected_direct_children=count,
            child_bitmap=bitmap,
            transform=transform,
            mask=inherited_mask or explicit_mask,
            mask_evidence=(
                "CONFIRMED_GROUP_60_ANCESTRY"
                if inherited_mask or explicit_mask
                else "NO_CONFIRMED_MASK_ANCESTRY"
            ),
            parent_path=path,
        )

    def make_shape(
        self,
        pos: int,
        parent_mask: bool,
        path: tuple[int, ...],
    ) -> tuple[ShapeNode, int] | None:
        parsed = _try_shape(self.payload, pos)
        if parsed is None:
            return None

        fields, size = parsed
        marker = fields["marker"]
        record = self.add_record("shape_record", pos, size, "CONFIRMED", marker)
        transform = Transform(
            x=float(fields["x"]),
            y=float(fields["y"]),
            sx=float(fields["sx"]),
            sy=float(fields["sy"]),
            rotation=float(fields["rotation"]),
            skew=float(fields["skew"]),
            source_span=record.span,
        )
        return ShapeNode(
            source_span=record.span,
            raw_record=record,
            shape_id=int(fields["shape_id"]),
            transform=transform,
            color_rgba=fields["color_rgba"],
            marker_hex=marker.hex(),
            mask=True if parent_mask else False,
            mask_evidence=(
                "CONFIRMED_GROUP_60_ANCESTRY"
                if parent_mask
                else "NO_CONFIRMED_MASK_ANCESTRY"
            ),
            parent_path=path,
        ), pos + size

    @staticmethod
    def mark_previous_contextual_mask_unresolved(group: GroupNode) -> None:
        if not group.children:
            return
        previous = group.children[-1]
        if isinstance(previous, ShapeNode) and previous.mask is not True:
            previous.mask = None
            previous.mask_evidence = "UNRESOLVED_CONTEXTUAL_ODD_LEAD_ON_NEXT_SIBLING"

    def consume_transform(
        self,
        pos: int,
        kind: str,
        evidence_state: str = "CONFIRMED",
    ) -> tuple[Transform, int] | None:
        parsed = _try_transform(self.payload, pos)
        if parsed is None:
            return None
        transform, size, marker = parsed
        self.add_record(kind, pos, size, evidence_state, marker)
        return transform, pos + size

    def consume_group_to_shape_control(
        self,
        group: GroupNode,
        pos: int,
        child_index: int,
    ) -> int:
        """Consume one observed inter-child 0x00 only under bounded structural proof.

        Real FH6 nested C_group samples can place a single 0x00 after a completed
        group child and before the next bitmap-declared shape. The byte is consumed
        only when the current offset is not itself a valid shape and a complete
        documented shape record begins exactly one byte later. Its higher semantic
        meaning remains unknown; no scanning or repeated skip is performed.
        """
        if child_index <= 0 or not group.children:
            return pos
        if not isinstance(group.children[-1], GroupNode):
            return pos
        if pos >= len(self.payload) or self.payload[pos] != 0x00:
            return pos
        if _try_shape(self.payload, pos) is not None:
            return pos
        if _try_shape(self.payload, pos + 1) is None:
            return pos

        record = self.add_record(
            "group_to_shape_control",
            pos,
            1,
            "CONFIRMED",
            b"\x00",
        )
        group.control_records.append(record)
        self.diagnostics.append(
            Diagnostic(
                severity="info",
                code="CGROUP_GROUP_TO_SHAPE_CONTROL_CONFIRMED",
                message=(
                    "a single 0x00 between a completed group child and the next "
                    "bitmap-declared shape was preserved as structural control; "
                    "the following complete shape framing validated the boundary"
                ),
                offset=pos,
                evidence_state="CONFIRMED",
            )
        )
        return pos + 1

    def parse_children(
        self,
        group: GroupNode,
        pos: int,
        *,
        bound_first_child_transform: Transform | None = None,
        allow_root_padding: bool = False,
    ) -> int:
        for child_index in range(group.expected_direct_children):
            if self.halted:
                break

            path = group.parent_path + (child_index,)
            expected_group = _child_is_group(group.child_bitmap, child_index)

            if allow_root_padding and child_index == 0 and not expected_group:
                start = pos
                while (
                    pos < len(self.payload)
                    and self.payload[pos] == 0x00
                    and self.payload[pos:pos + 2] != b"\x00\x02"
                ):
                    pos += 1
                if pos > start:
                    group.control_records.append(
                        self.add_record("zero_padding", start, pos - start, "CONFIRMED")
                    )

            if expected_group:
                pending_transform = (
                    bound_first_child_transform if child_index == 0 else None
                )
                if pending_transform is None:
                    consumed = self.consume_transform(pos, "group_transform")
                    if consumed is not None:
                        pending_transform, pos = consumed

                if _try_transform(self.payload, pos) is not None:
                    group.children.append(
                        self.unknown_tail(
                            pos,
                            path,
                            "consecutive group transforms are not assigned semantically in Milestone 2",
                        )
                    )
                    break

                counted = _try_counted_group(self.payload, pos)
                markerless = (
                    None
                    if counted is not None or pending_transform is None
                    else _try_markerless_group(self.payload, pos)
                )
                if counted is not None:
                    count, bitmap, header_size, marker = counted
                    child = self.make_group(
                        header_pos=pos,
                        header_size=header_size,
                        marker=marker,
                        count=count,
                        bitmap=bitmap,
                        transform=pending_transform or Transform(),
                        inherited_mask=group.mask,
                        path=path,
                        kind="counted_group_header",
                    )
                elif markerless is not None:
                    count, bitmap, header_size = markerless
                    child = self.make_group(
                        header_pos=pos,
                        header_size=header_size,
                        marker=None,
                        count=count,
                        bitmap=bitmap,
                        transform=pending_transform or Transform(),
                        inherited_mask=group.mask,
                        path=path,
                        kind="markerless_group_header",
                    )
                else:
                    group.children.append(
                        self.unknown_tail(
                            pos,
                            path,
                            "parent bitmap requires a group child but no documented group framing matched",
                        )
                    )
                    break

                pos += child.header_span.length
                first_child_transform = None
                if child.expected_direct_children:
                    inline = self.consume_transform(
                        pos,
                        "inline_group_transform",
                        evidence_state="PROVISIONAL",
                    )
                    if inline is not None:
                        inline_transform, pos = inline
                        child.control_records.append(self.records[-1])
                        if _child_is_group(child.child_bitmap, 0):
                            first_child_transform = inline_transform
                        elif child.transform == Transform():
                            child.transform = inline_transform
                        else:
                            self.diagnostics.append(
                                Diagnostic(
                                    severity="warning",
                                    code="CGROUP_MULTIPLE_GROUP_TRANSFORMS",
                                    message=(
                                        "a group has both a preceding transform and an inline transform; "
                                        "the inline record is preserved but not composed"
                                    ),
                                    offset=(
                                        inline_transform.source_span.offset
                                        if inline_transform.source_span
                                        else pos
                                    ),
                                    evidence_state="PROVISIONAL",
                                )
                            )

                pos = self.parse_children(
                    child,
                    pos,
                    bound_first_child_transform=first_child_transform,
                )
                child.source_span = SourceSpan(
                    child.header_span.offset,
                    max(child.header_span.length, pos - child.header_span.offset),
                )
                child.complete = (
                    not self.halted
                    and child.parsed_direct_children == child.expected_direct_children
                )
                group.children.append(child)
                continue

            pos = self.consume_group_to_shape_control(group, pos, child_index)

            if child_index == 0:
                inline = self.consume_transform(
                    pos,
                    "inline_group_transform",
                    evidence_state="PROVISIONAL",
                )
                if inline is not None:
                    inline_transform, pos = inline
                    group.control_records.append(self.records[-1])
                    if group.transform == Transform():
                        group.transform = inline_transform
                    else:
                        self.diagnostics.append(
                            Diagnostic(
                                severity="warning",
                                code="CGROUP_MULTIPLE_GROUP_TRANSFORMS",
                                message=(
                                    "a group has both a preceding transform and an inline transform; "
                                    "the inline record is preserved but not composed"
                                ),
                                offset=(
                                    inline_transform.source_span.offset
                                    if inline_transform.source_span
                                    else pos
                                ),
                                evidence_state="PROVISIONAL",
                            )
                        )

            parsed_shape = self.make_shape(pos, group.mask, path)
            if parsed_shape is None:
                group.children.append(
                    self.unknown_tail(
                        pos,
                        path,
                        "parent bitmap requires a shape child but no documented 31/32-byte shape framing matched",
                    )
                )
                break

            shape, pos = parsed_shape
            if shape.marker_hex == "0102":
                self.mark_previous_contextual_mask_unresolved(group)
            group.children.append(shape)

        group.complete = (
            not self.halted
            and group.parsed_direct_children == group.expected_direct_children
        )
        return pos


def decode_cgroup_bytes(raw: bytes | bytearray | memoryview) -> CGroupScene:
    payload, container = inflate_cgroup(raw)
    if len(payload) < 0x24 or payload[:4] != b"gyvl":
        raise CGroupDecodeError("C_group payload is shorter than the documented root header")

    version = _u32(payload, 0x04)
    root_transform_marker = payload[0x0C]
    root_x = _f32(payload, 0x0D)
    root_y = _f32(payload, 0x11)
    root_scale = _f32(payload, 0x15)
    root_rotation = _f32(payload, 0x19)
    if not all(math.isfinite(v) for v in (root_x, root_y, root_scale, root_rotation)):
        raise CGroupDecodeError("root transform contains a non-finite value")
    if root_scale == 0.0:
        raise CGroupDecodeError("root transform scale is zero")

    root_group_marker = payload[0x1D]
    if root_group_marker not in (0x20, 0x60):
        raise CGroupDecodeError(
            f"root group marker at 0x1d is 0x{root_group_marker:02x}, expected 0x20 or 0x60"
        )

    root_count = _u16(payload, 0x1E)
    root_blocks = payload[0x20]
    expected_blocks = (root_count + 7) // 8
    if root_blocks != expected_blocks:
        raise CGroupDecodeError(
            "root child block count does not match direct child count "
            f"({root_blocks} stored, {expected_blocks} expected)"
        )

    layer_start = 0x24 + root_blocks
    if layer_start > len(payload):
        raise CGroupDecodeError("root child bitmap is truncated")
    root_bitmap = payload[0x24:layer_start]

    parser = _Parser(payload)
    parser.add_record(
        "cgroup_preamble",
        0,
        0x1D,
        "CONFIRMED",
        bytes([root_transform_marker]),
    )
    root_header = parser.add_record(
        "root_group_header",
        0x1D,
        layer_start - 0x1D,
        "CONFIRMED",
        bytes([root_group_marker]),
    )

    root = GroupNode(
        header_span=root_header.span,
        source_span=root_header.span,
        raw_header=root_header,
        marker_hex=f"{root_group_marker:02x}",
        expected_direct_children=root_count,
        child_bitmap=root_bitmap,
        transform=Transform(
            x=root_x,
            y=root_y,
            sx=root_scale,
            sy=root_scale,
            rotation=root_rotation,
            source_span=SourceSpan(0x0C, 17),
        ),
        mask=root_group_marker == 0x60,
        mask_evidence=(
            "CONFIRMED_GROUP_60_ANCESTRY"
            if root_group_marker == 0x60
            else "NO_CONFIRMED_MASK_ANCESTRY"
        ),
        parent_path=(),
    )

    pos = parser.parse_children(root, layer_start, allow_root_padding=True)
    root.source_span = SourceSpan(
        root.header_span.offset,
        max(root.header_span.length, pos - root.header_span.offset),
    )

    if not parser.halted and pos < len(payload):
        trailing = parser.add_record(
            "trailing_bytes",
            pos,
            len(payload) - pos,
            "UNKNOWN",
        )
        root.control_records.append(trailing)
        parser.diagnostics.append(
            Diagnostic(
                severity="info",
                code="CGROUP_TRAILING_BYTES_PRESERVED",
                message="bytes after the completed root group are preserved without interpretation",
                offset=pos,
                evidence_state="UNKNOWN",
            )
        )

    expected_offset = 0
    coverage_ok = True
    for record in parser.records:
        if record.span.offset != expected_offset:
            coverage_ok = False
            break
        expected_offset = record.span.end
    lossless = coverage_ok and expected_offset == len(payload)
    if not lossless:
        parser.diagnostics.append(
            Diagnostic(
                severity="error",
                code="CGROUP_RECORD_COVERAGE_GAP",
                message="raw record spans do not provide contiguous lossless payload coverage",
                offset=expected_offset,
                evidence_state="CONFIRMED",
            )
        )

    parser.diagnostics.append(
        Diagnostic(
            severity="info",
            code="CGROUP_GENERATION_UNRESOLVED",
            message=(
                f"root transform marker 0x{root_transform_marker:02x} is preserved; "
                "Milestone 2 does not infer record generation from that byte alone"
            ),
            offset=0x0C,
            evidence_state="UNKNOWN",
        )
    )

    return CGroupScene(
        container=container,
        version=version,
        generation=None,
        root=root,
        records=tuple(parser.records),
        diagnostics=tuple(parser.diagnostics),
        payload_length=len(payload),
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        lossless_record_coverage=lossless,
    )


def decode_cgroup_file(path: str | Path) -> CGroupScene:
    return decode_cgroup_bytes(Path(path).read_bytes())


def decode_cgroup_file_to_json(path: str | Path, *, indent: int = 2) -> str:
    return decode_cgroup_file(path).to_json(indent=indent)
