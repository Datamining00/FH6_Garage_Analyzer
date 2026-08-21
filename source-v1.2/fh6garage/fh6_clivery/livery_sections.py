from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from .cgroup import _child_is_group, _try_counted_group, _try_markerless_group, _try_shape
from .diagnostics import Diagnostic
from .records import RawRecord, SourceSpan, Transform
from .scene import GroupNode, ShapeNode, tree_stats

EMPTY_SECTION_SIZE = 23
POPULATED_SECTION_REMNANT_SIZE = 18
FINAL_SECTION_STATE_SIZE = 1
LIVERY_TRAILER_SIZE = 9


class LiverySectionDecodeError(ValueError):
    def __init__(self, message: str, offset: int, path: tuple[int, ...] = ()) -> None:
        super().__init__(message)
        self.offset = offset
        self.path = path


@dataclass(frozen=True)
class LiverySectionResult:
    slot: int
    name: str
    declared_count: int
    parsed_leaf_count: int
    section_start: int
    tree_end: int
    section_end: int
    root: GroupNode | None
    unknown_spans: tuple[SourceSpan, ...]
    diagnostics: tuple[Diagnostic, ...]
    complete: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "name": self.name,
            "declared_count": self.declared_count,
            "parsed_leaf_count": self.parsed_leaf_count,
            "section_start": self.section_start,
            "tree_end": self.tree_end,
            "section_end": self.section_end,
            "source_span": SourceSpan(self.section_start, self.section_end - self.section_start).to_dict(),
            "complete": self.complete,
            "root": self.root.to_dict() if self.root else None,
            "unknown_spans": [span.to_dict() for span in self.unknown_spans],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True)
class LiveryArtworkResult:
    sections: tuple[LiverySectionResult, ...]
    records: tuple[RawRecord, ...]
    diagnostics: tuple[Diagnostic, ...]
    body_start: int
    body_end: int
    lossless_record_coverage: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "body_start": self.body_start,
            "body_end": self.body_end,
            "lossless_record_coverage": self.lossless_record_coverage,
            "sections": [section.to_dict() for section in self.sections],
            "records": [record.to_dict() for record in self.records],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True)
class _GroupHeader:
    pos: int
    size: int
    count: int
    bitmap: bytes
    marker: int | None


@dataclass(frozen=True)
class _GroupCandidate:
    start: int
    header: _GroupHeader
    transform: Transform
    transform_record: RawRecord | None
    control_record: RawRecord | None
    mask_from_suffix: bool


class _Parser:
    def __init__(self, payload: bytes, body_start: int, body_end: int) -> None:
        self.payload = payload
        self.body_start = body_start
        self.body_end = body_end
        self.records: list[RawRecord] = []
        self.diagnostics: list[Diagnostic] = []

    def add_record(self, kind: str, offset: int, length: int, evidence: str, marker: bytes | None = None) -> RawRecord:
        rec = RawRecord(kind, SourceSpan(offset, length), self.payload[offset:offset + length], evidence, marker.hex() if marker else None)
        self.records.append(rec)
        return rec

    def fail(self, message: str, pos: int, path: tuple[int, ...]) -> LiverySectionDecodeError:
        return LiverySectionDecodeError(message, pos, path)

    def finite_transform(self, pos: int) -> tuple[float, float, float, float] | None:
        if pos < self.body_start or pos + 16 > self.body_end:
            return None
        values = struct.unpack_from("<ffff", self.payload, pos)
        return values if all(math.isfinite(v) for v in values) and values[2] != 0.0 else None

    def counted_header(self, pos: int) -> _GroupHeader | None:
        parsed = _try_counted_group(self.payload, pos)
        if parsed is None:
            return None
        count, bitmap, size, marker = parsed
        return None if pos + size > self.body_end else _GroupHeader(pos, size, count, bitmap, marker)

    def markerless_header(self, pos: int) -> _GroupHeader | None:
        parsed = _try_markerless_group(self.payload, pos)
        if parsed is None:
            return None
        count, bitmap, size = parsed
        return None if pos + size > self.body_end else _GroupHeader(pos, size, count, bitmap, None)

    @staticmethod
    def shifted_markerless(a: _GroupHeader | None, b: _GroupHeader | None) -> bool:
        return bool(a and b and a.count == b.count * 256 and len(a.bitmap) == len(b.bitmap) * 256)

    def shape_at(self, pos: int) -> tuple[dict[str, object], int] | None:
        parsed = _try_shape(self.payload, pos)
        return parsed if parsed is not None and pos + parsed[1] <= self.body_end else None

    def make_shape(self, pos: int, path: tuple[int, ...], inherited_mask: bool) -> tuple[ShapeNode, int]:
        parsed = self.shape_at(pos)
        if parsed is None:
            raise self.fail("parent bitmap requires a shape but no complete documented 31/32-byte shape framing matched", pos, path)
        f, size = parsed
        marker = f["marker"]
        rec = self.add_record("livery_shape_record", pos, size, "CONFIRMED", marker)
        transform = Transform(float(f["x"]), float(f["y"]), float(f["sx"]), float(f["sy"]), float(f["rotation"]), float(f["skew"]), rec.span)
        mask = True if inherited_mask else None
        evidence = "CONFIRMED_GROUP_60_ANCESTRY" if inherited_mask else "LIVERY_RECORD_MASK_SEMANTICS_UNRESOLVED_M3"
        return ShapeNode(rec.span, rec, int(f["shape_id"]), transform, f["color_rgba"], marker.hex(), mask, evidence, path), pos + size

    def successor_headers(self, after: int) -> list[tuple[_GroupHeader, int, int, str]]:
        out: list[tuple[_GroupHeader, int, int, str]] = []
        c0 = self.counted_header(after)
        c1 = self.counted_header(after + 1) if after + 1 <= self.body_end else None
        if c0:
            out.append((c0, after, 0, ""))
        if c1:
            out.append((c1, after, 1, "livery_group_successor_control"))
        trailer = after + 9 <= self.body_end and self.payload[after] == 0x21 and self.payload[after + 7:after + 9] == b"\x09\x00"
        if trailer:
            ct = self.counted_header(after + 9)
            if ct:
                out.append((ct, after, 9, "livery_group_successor_trailer"))

        m0 = self.markerless_header(after)
        m1 = self.markerless_header(after + 1) if after + 1 <= self.body_end else None
        if self.shifted_markerless(m0, m1):
            out.append((m1, after, 1, "livery_group_successor_control"))  # type: ignore[arg-type]
        else:
            if m0:
                out.append((m0, after, 0, ""))
            if m1:
                out.append((m1, after, 1, "livery_group_successor_control"))
        if trailer:
            mt = self.markerless_header(after + 9)
            if mt:
                out.append((mt, after, 9, "livery_group_successor_trailer"))
        return out

    def _candidate(self, start: int, values: tuple[float, float, float, float], header: _GroupHeader, transform_len: int, marker_hex: str | None, control_pos: int, control_len: int, control_kind: str, sy: float | None, suffix: int | None, evidence: str, transform_kind: str = "livery_group_transform") -> _GroupCandidate:
        tr_rec = RawRecord(transform_kind, SourceSpan(start, transform_len), self.payload[start:start + transform_len], evidence, marker_hex)
        ctrl = None
        if control_len:
            ctrl = RawRecord(control_kind, SourceSpan(control_pos, control_len), self.payload[control_pos:control_pos + control_len], "CONFIRMED" if control_len == 1 else "PROVISIONAL", None)
        x, y, sx, rotation = values
        return _GroupCandidate(start, header, Transform(x, y, sx, sy if sy is not None else sx, rotation, 0.0, tr_rec.span), tr_rec, ctrl, suffix == 0x70)

    def group_candidates(self, pos: int, *, allow_inline_root_transform: bool) -> list[_GroupCandidate]:
        direct = self.counted_header(pos)
        if direct:
            return [_GroupCandidate(pos, direct, Transform(), None, None, False)]
        result: list[_GroupCandidate] = []

        if allow_inline_root_transform:
            values = self.finite_transform(pos)
            if values is not None:
                base = pos + 16
                ext = [(0, None, None)]
                if base + 5 <= self.body_end and self.payload[base] in (0x30, 0x70):
                    sy = struct.unpack_from("<f", self.payload, base + 1)[0]
                    if math.isfinite(sy) and sy != 0.0:
                        ext.insert(0, (5, sy, self.payload[base]))
                for ext_len, sy, suffix in ext:
                    for header, cp, cl, ck in self.successor_headers(base + ext_len):
                        cand = self._candidate(pos, values, header, 16 + ext_len, f"{suffix:02x}" if suffix is not None else None, cp, cl, ck, sy, suffix, "CONFIRMED" if ext_len == 0 else "PROVISIONAL", "livery_inline_group_transform")
                        result.append(cand)
                if result:
                    return result

        leads: list[bytes] = []
        if self.payload[pos:pos + 2] == b"\x00\x01":
            leads.append(b"\x00\x01")
        if self.payload[pos:pos + 1] in (b"\x00", b"\x01"):
            leads.append(self.payload[pos:pos + 1])
        for lead in leads:
            values = self.finite_transform(pos + len(lead))
            if values is None:
                continue
            base = pos + len(lead) + 16
            ext = [(0, None, None)]
            if base + 5 <= self.body_end and self.payload[base] in (0x30, 0x70):
                sy = struct.unpack_from("<f", self.payload, base + 1)[0]
                if math.isfinite(sy) and sy != 0.0:
                    ext.insert(0, (5, sy, self.payload[base]))
            for ext_len, sy, suffix in ext:
                for header, cp, cl, ck in self.successor_headers(base + ext_len):
                    evidence = "PROVISIONAL" if len(lead) == 2 or suffix == 0x70 else "CONFIRMED"
                    result.append(self._candidate(pos, values, header, len(lead) + 16 + ext_len, lead.hex(), cp, cl, ck, sy, suffix, evidence))
        return result

    def make_group(self, candidate: _GroupCandidate, path: tuple[int, ...], inherited_mask: bool) -> GroupNode:
        if candidate.transform_record:
            self.records.append(candidate.transform_record)
        if candidate.control_record:
            self.records.append(candidate.control_record)
        h = candidate.header
        marker = bytes([h.marker]) if h.marker is not None else None
        rec = self.add_record("livery_counted_group_header" if marker else "livery_markerless_group_header", h.pos, h.size, "CONFIRMED", marker)
        explicit = h.marker == 0x60
        mask = inherited_mask or explicit
        evidence = "CONFIRMED_GROUP_60_ANCESTRY" if mask else ("DOCUMENTED_70_SUFFIX_MASK_PROVISIONAL" if candidate.mask_from_suffix else "NO_CONFIRMED_MASK_ANCESTRY")
        return GroupNode(rec.span, SourceSpan(candidate.start, rec.span.end - candidate.start), rec, marker.hex() if marker else "", h.count, h.bitmap, candidate.transform, mask, evidence, path)

    def parse_group_candidates(self, candidates: list[_GroupCandidate], path: tuple[int, ...], inherited_mask: bool) -> tuple[GroupNode, int]:
        if not candidates:
            raise self.fail("parent bitmap requires a group but no bounded livery group framing matched", self.body_start, path)
        start = candidates[0].start
        last: LiverySectionDecodeError | None = None
        for candidate in candidates:
            rc, dc = len(self.records), len(self.diagnostics)
            try:
                return self.parse_group(candidate, path, inherited_mask)
            except LiverySectionDecodeError as exc:
                del self.records[rc:]
                del self.diagnostics[dc:]
                last = exc
        message = "all bounded livery group candidates failed structural child parsing"
        if last:
            message += f": {last}"
        raise self.fail(message, start, path)

    def parse_group(self, candidate: _GroupCandidate, path: tuple[int, ...], inherited_mask: bool) -> tuple[GroupNode, int]:
        group = self.make_group(candidate, path, inherited_mask)
        pos = candidate.header.pos + candidate.header.size
        for i in range(group.expected_direct_children):
            child_path = path + (i,)
            if _child_is_group(group.child_bitmap, i):
                candidates = self.group_candidates(pos, allow_inline_root_transform=False)
                if not candidates:
                    raise self.fail("parent bitmap requires a group but no bounded livery group framing matched", pos, child_path)
                child, pos = self.parse_group_candidates(candidates, child_path, group.mask)
                group.children.append(child)
            else:
                child, pos = self.make_shape(pos, child_path, group.mask)
                group.children.append(child)
        group.complete = group.parsed_direct_children == group.expected_direct_children
        group.source_span = SourceSpan(candidate.start, pos - candidate.start)
        return group, pos

    def parse_section_root(self, slot: int, pos: int) -> tuple[GroupNode, int]:
        h = self.markerless_header(pos)
        if h is None or h.count == 0:
            raise self.fail("populated section does not begin with a valid markerless section root", pos, (slot,))
        rec = self.add_record("livery_section_root_header", pos, h.size, "CONFIRMED")
        root = GroupNode(rec.span, rec.span, rec, "", h.count, h.bitmap, Transform(), False, "NO_CONFIRMED_MASK_ANCESTRY", (slot,))
        cursor = pos + h.size
        for i in range(h.count):
            path = (slot, i)
            if _child_is_group(h.bitmap, i):
                candidates = self.group_candidates(cursor, allow_inline_root_transform=i == 0)
                if not candidates:
                    raise self.fail("section bitmap requires a group but no bounded livery group framing matched", cursor, path)
                child, cursor = self.parse_group_candidates(candidates, path, root.mask)
                root.children.append(child)
            else:
                child, cursor = self.make_shape(cursor, path, root.mask)
                root.children.append(child)
        root.complete = root.parsed_direct_children == root.expected_direct_children
        root.source_span = SourceSpan(pos, cursor - pos)
        return root, cursor

    def validate_empty(self, pos: int, later: bool) -> bool:
        if pos + 23 > self.body_end:
            return False
        if later:
            h = self.markerless_header(pos)
            return bool(h and h.count == 0 and h.size == 6 and self.finite_transform(pos + 6))
        return self.finite_transform(pos) is not None

    def validate_next(self, pos: int, declared: int, later: bool) -> bool:
        if declared == 0:
            return self.validate_empty(pos, later)
        h = self.markerless_header(pos)
        return bool(h and h.count > 0)

    def consume_populated_boundary(self, slot: int, tree_end: int, counts: tuple[int, ...]) -> int:
        later = any(counts[slot + 1:])
        if later:
            if tree_end + 18 > self.body_end or self.finite_transform(tree_end + 1) is None:
                raise self.fail("parsed populated section is not followed by a structurally valid 18-byte remnant", tree_end, (slot,))
            end = tree_end + 18
            if slot + 1 < len(counts) and not self.validate_next(end, counts[slot + 1], any(counts[slot + 2:])):
                raise self.fail("18-byte remnant candidate did not lead to the structurally valid next section slot", tree_end, (slot,))
            self.add_record("livery_section_remnant", tree_end, 18, "CONFIRMED")
            return end
        if tree_end + 1 > self.body_end:
            raise self.fail("final populated section has no terminal state byte", tree_end, (slot,))
        end = tree_end + 1
        if slot + 1 < len(counts) and not self.validate_empty(end, False):
            raise self.fail("final populated section terminal state is not followed by the expected trailing empty scaffold", tree_end, (slot,))
        self.add_record("livery_section_terminal_state", tree_end, 1, "CONFIRMED")
        return end

    def consume_empty(self, slot: int, pos: int, counts: tuple[int, ...]) -> int:
        later = any(counts[slot + 1:])
        if not self.validate_empty(pos, later):
            raise self.fail("empty section does not match the bounded 23-byte scaffold", pos, (slot,))
        self.add_record("livery_empty_section_scaffold", pos, 23, "CONFIRMED")
        end = pos + 23
        if slot + 1 < len(counts) and not self.validate_next(end, counts[slot + 1], any(counts[slot + 2:])):
            raise self.fail("empty scaffold did not lead to the structurally valid next section slot", end, (slot,))
        return end

    def coverage(self) -> bool:
        expected = self.body_start
        for record in self.records:
            if record.span.offset != expected:
                return False
            expected = record.span.end
        return expected == self.body_end


def decode_livery_sections(payload: bytes, body_start: int, body_end: int, section_names: tuple[str, ...], counts: tuple[int, ...]) -> LiveryArtworkResult:
    if len(section_names) != len(counts):
        raise ValueError("section names/counts length mismatch")
    parser = _Parser(payload, body_start, body_end)
    sections: list[LiverySectionResult] = []
    pos = body_start

    for slot, (name, declared) in enumerate(zip(section_names, counts)):
        start = pos
        local: list[Diagnostic] = []
        try:
            if declared == 0:
                pos = parser.consume_empty(slot, pos, counts)
                sections.append(LiverySectionResult(slot, name, 0, 0, start, start, pos, None, (), (), True))
                continue
            root, tree_end = parser.parse_section_root(slot, pos)
            leaves = int(tree_stats(root)["leaf_count"])
            pos = parser.consume_populated_boundary(slot, tree_end, counts)
            if leaves == declared:
                local.append(Diagnostic("info", "LIVERY_SECTION_LEAF_COUNT_CONFIRMED", f"section {name} parsed {leaves} physical leaves, matching the declared counter", start, "CONFIRMED"))
            else:
                has_raster = False
                stack = [root]
                while stack:
                    node = stack.pop()
                    for child in node.children:
                        if isinstance(child, ShapeNode) and child.shape_id & 0x8000:
                            has_raster = True
                        elif isinstance(child, GroupNode):
                            stack.append(child)
                local.append(Diagnostic("warning", "LIVERY_SECTION_LOGICAL_COUNT_DIFFERS" if has_raster else "LIVERY_SECTION_LEAF_COUNT_MISMATCH", f"section {name} declares {declared} logical decals but {leaves} physical leaves were parsed; raster descriptor weighting is not interpreted in Milestone 3", start, "UNKNOWN" if has_raster else "PROVISIONAL"))
            sections.append(LiverySectionResult(slot, name, declared, leaves, start, tree_end, pos, root, (), tuple(local), root.complete))
            parser.diagnostics.extend(local)
        except LiverySectionDecodeError as exc:
            unknown_start = max(exc.offset, start)
            span = SourceSpan(body_end, 0)
            if unknown_start < body_end:
                span = parser.add_record("livery_unknown_tail", unknown_start, body_end - unknown_start, "UNKNOWN").span
            diag = Diagnostic("warning", "LIVERY_SECTION_UNKNOWN_TAIL", str(exc) + "; remaining artwork bytes were preserved without scanning for a later plausible section", exc.offset, "UNKNOWN")
            parser.diagnostics.append(diag)
            sections.append(LiverySectionResult(slot, name, declared, 0, start, unknown_start, body_end, None, (span,), (diag,), False))
            for later_slot in range(slot + 1, len(counts)):
                unavailable = Diagnostic("warning", "LIVERY_SECTION_UNAVAILABLE_AFTER_UNKNOWN", "section boundary is unavailable after an earlier unresolved artwork span", body_end, "UNKNOWN")
                sections.append(LiverySectionResult(later_slot, section_names[later_slot], counts[later_slot], 0, body_end, body_end, body_end, None, (), (unavailable,), False))
            pos = body_end
            break

    lossless = parser.coverage()
    parser.diagnostics.append(Diagnostic("info" if lossless else "error", "LIVERY_ARTWORK_RECORD_COVERAGE", "artwork RawRecord spans cover body_start through body_end contiguously" if lossless else "artwork RawRecord spans do not cover body_start through body_end contiguously", body_start, "CONFIRMED"))
    if pos != body_end:
        parser.diagnostics.append(Diagnostic("error", "LIVERY_SECTION_WALK_DID_NOT_END_AT_BODY_BOUNDARY", f"section walk ended at 0x{pos:x}, expected body_end 0x{body_end:x}", pos, "CONFIRMED"))
    return LiveryArtworkResult(tuple(sections), tuple(parser.records), tuple(parser.diagnostics), body_start, body_end, lossless)
