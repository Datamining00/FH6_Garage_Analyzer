from __future__ import annotations

import json
import mmap
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

class GlbViewerError(RuntimeError):
    pass


LIVERY_ELIGIBILITY_POLICIES = {
    "legacy",
    "strict",
    "declared_confirmed",
}


def normalize_livery_eligibility_policy(value: str | None) -> str:
    key = str(value or "legacy").strip().casefold().replace("+", "_").replace(" ", "_")
    aliases = {
        "legacy": "legacy",
        "strict": "strict",
        "declared_confirmed": "declared_confirmed",
        "declared__confirmed": "declared_confirmed",
        "confirmed": "declared_confirmed",
    }
    resolved = aliases.get(key, key)
    if resolved not in LIVERY_ELIGIBILITY_POLICIES:
        raise GlbViewerError(
            f"Unsupported livery eligibility policy {value!r}; expected "
            "legacy, strict, or declared_confirmed."
        )
    return resolved




def _neutral_geometry_excluded(
    extras: dict,
    cleanup_ab: bool,
    cleanup_c: bool,
) -> tuple[bool, str]:
    role = str(extras.get("kfps_role") or "trim").casefold()
    if role == "hidden":
        return True, "legacy_hidden"
    if cleanup_ab and bool(extras.get("kfps_neutral_ab_hidden", False)):
        return True, "neutral_ab"
    if cleanup_c and bool(extras.get("kfps_neutral_c_candidate", False)):
        return True, "neutral_c"
    return False, ""

@dataclass(frozen=True)
class GlbSceneData:
    positions: np.ndarray
    normals: np.ndarray
    colors: np.ndarray
    uv3: np.ndarray
    allowed_sides: np.ndarray
    projection_sides: np.ndarray
    direct_uv: np.ndarray
    indices: np.ndarray
    mesh_count: int
    triangle_count: int
    role_counts: dict[str, int]
    uv3_meshes: int
    projected_meshes: int
    excluded_livery_meshes: int
    inferred_uv3_meshes: int
    promoted_livery_meshes: int
    expanded_allowed_meshes: int
    uv3_without_mask_overlap: int
    inferred_projection_meshes: int
    projection_no_overlap_meshes: int
    selected_uv_channel_counts: dict[int, int]
    alternate_uv_channel_primitives: int
    uv_channel_candidates_without_overlap: int
    selected_uv_mask_evidence_meshes: int
    selected_uv_without_mask_overlap: int
    projection_minimum: np.ndarray
    projection_maximum: np.ndarray
    projection_valid: np.ndarray
    primitive_diagnostics: tuple[dict, ...]
    livery_uv_channel: int
    livery_eligibility_policy: str
    neutral_cleanup_ab_enabled: bool
    neutral_cleanup_c_enabled: bool
    neutral_ab_excluded_meshes: int
    neutral_c_excluded_meshes: int
    bounds_min: np.ndarray
    bounds_max: np.ndarray


_COMPONENT_DTYPES = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
_TYPE_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _read_glb(path: Path) -> tuple[dict, memoryview]:
    """Read GLB metadata while memory-mapping the binary payload when possible.

    This avoids holding a second full Python bytes copy of large cached GLBs. The
    returned memoryview owns a reference to the mmap for as long as decoding uses
    it.
    """
    try:
        source = path.open("rb")
    except OSError as exc:
        raise GlbViewerError(f"Could not open GLB: {exc}") from exc
    try:
        mapped = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        source.close()
        data = path.read_bytes()
        root = memoryview(data)
    else:
        source.close()
        root = memoryview(mapped)
    if len(root) < 20 or bytes(root[:4]) != b"glTF":
        raise GlbViewerError("Not a GLB file (missing glTF magic).")
    version, total = struct.unpack_from("<II", root, 4)
    if version != 2 or total > len(root):
        raise GlbViewerError(f"Unsupported or truncated GLB: version={version}, length={total}.")
    offset = 12
    document = None
    binary = None
    while offset + 8 <= total:
        length, chunk_type = struct.unpack_from("<II", root, offset)
        offset += 8
        if offset + length > total:
            raise GlbViewerError("GLB chunk extends past the end of the file.")
        chunk = root[offset:offset + length]
        offset += length
        if chunk_type == 0x4E4F534A:
            document = json.loads(bytes(chunk).rstrip(b" \x00").decode("utf-8"))
        elif chunk_type == 0x004E4942 and binary is None:
            binary = chunk
    if not isinstance(document, dict) or binary is None:
        raise GlbViewerError("GLB has no JSON document or binary buffer.")
    return document, binary


def _accessor_array(document: dict, binary: memoryview, accessor_index: int) -> np.ndarray:
    try:
        accessor = document["accessors"][accessor_index]
        view = document["bufferViews"][accessor["bufferView"]]
        component_type = int(accessor["componentType"])
        dtype = _COMPONENT_DTYPES[component_type]
        width = _TYPE_WIDTH[str(accessor["type"])]
        count = int(accessor["count"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GlbViewerError(f"Invalid accessor {accessor_index}.") from exc
    if accessor.get("sparse") is not None:
        raise GlbViewerError("Sparse accessors are not supported by this M3 viewer.")
    component_size = np.dtype(dtype).itemsize
    element_size = component_size * width
    stride = int(view.get("byteStride", element_size))
    view_offset = int(view.get("byteOffset", 0))
    accessor_offset = int(accessor.get("byteOffset", 0))
    start = view_offset + accessor_offset
    end = start + (count - 1) * stride + element_size if count else start
    if start < 0 or end > len(binary):
        raise GlbViewerError(f"Accessor {accessor_index} points outside the GLB binary buffer.")
    if stride == element_size:
        arr = np.frombuffer(binary, dtype=dtype, count=count * width, offset=start)
        return arr.reshape((count, width)).copy()
    raw = np.ndarray(
        shape=(count, width),
        dtype=dtype,
        buffer=binary,
        offset=start,
        strides=(stride, component_size),
    )
    return raw.copy()



def _direct_uv_mask_evidence(uv: np.ndarray, indices: np.ndarray, mask_pages: np.ndarray | None) -> tuple[int, int, tuple[int, ...]]:
    """Return (section_bits, intersected_texels, per-slot counts) for one UV stream.

    Indexed UV triangles are rasterized on the exact mask texel grid.  Evidence
    is purely geometric: no vehicle/model/material/part names, percentage
    thresholds, UV-range heuristics, or sample-count knobs are used.
    """
    if mask_pages is None:
        return 0, 0, (0,) * 11
    pages = np.asarray(mask_pages)
    if pages.ndim != 4 or pages.shape[0] != 3 or pages.shape[3] != 4:
        return 0, 0, (0,) * 11
    if uv.ndim != 2 or uv.shape[1] != 2 or not len(uv):
        return 0, 0, (0,) * 11
    raw_indices = np.asarray(indices, dtype=np.int64).reshape(-1)
    if len(raw_indices) < 3 or len(raw_indices) % 3 != 0:
        return 0, 0, (0,) * 11
    tri = raw_indices.reshape(-1, 3)
    if tri.min(initial=0) < 0 or int(tri.max(initial=0)) >= len(uv):
        return 0, 0, (0,) * 11
    tuv = np.asarray(uv[tri], dtype=np.float64)
    finite = np.isfinite(tuv).all(axis=(1, 2))
    tuv = tuv[finite]
    if not len(tuv):
        return 0, 0, (0,) * 11

    h, w = int(pages.shape[1]), int(pages.shape[2])
    # FH6/KFPS direct livery convention.  The selected source channel is
    # normalized into the shader's inUV3 attribute after this evidence test.
    pixel = np.empty_like(tuv, dtype=np.float64)
    pixel[:, :, 0] = tuv[:, :, 0] * 0.5 * (w - 1)
    pixel[:, :, 1] = tuv[:, :, 1] * (h - 1)
    min_xy = pixel.min(axis=1)
    max_xy = pixel.max(axis=1)
    intersects = (
        (max_xy[:, 0] >= 0.0) & (min_xy[:, 0] <= w - 1)
        & (max_xy[:, 1] >= 0.0) & (min_xy[:, 1] <= h - 1)
    )
    pixel = pixel[intersects]
    if not len(pixel):
        return 0, 0, (0,) * 11
    x0 = max(0, int(np.floor(pixel[:, :, 0].min())))
    y0 = max(0, int(np.floor(pixel[:, :, 1].min())))
    x1 = min(w - 1, int(np.ceil(pixel[:, :, 0].max())))
    y1 = min(h - 1, int(np.ceil(pixel[:, :, 1].max())))
    if x1 < x0 or y1 < y0:
        return 0, 0, (0,) * 11

    from PIL import Image, ImageDraw
    coverage_image = Image.new("1", (x1 - x0 + 1, y1 - y0 + 1), 0)
    draw = ImageDraw.Draw(coverage_image)
    for triangle in pixel:
        points = [(float(px - x0), float(py - y0)) for px, py in triangle]
        draw.polygon(points, fill=1, outline=1)
        draw.line(points + [points[0]], fill=1, width=1)
    coverage = np.asarray(coverage_image, dtype=bool)
    if not np.any(coverage):
        return 0, 0, (0,) * 11

    bits = 0
    counts = []
    for slot in range(11):
        page, channel = divmod(slot, 4)
        section = pages[page, y0:y1 + 1, x0:x1 + 1, channel] != 0
        count = int(np.count_nonzero(section & coverage)) if section.shape == coverage.shape else 0
        counts.append(count)
        if count:
            bits |= 1 << slot
    return bits, int(sum(counts)), tuple(counts)


def _infer_direct_allowed_mask(uv: np.ndarray, indices: np.ndarray, mask_pages: np.ndarray | None) -> int:
    return _direct_uv_mask_evidence(uv, indices, mask_pages)[0]


def _uv_channel_candidates(
    document: dict, binary: memoryview, attrs: dict, vertex_count: int, channels: set[int] | None = None
) -> list[tuple[int, np.ndarray]]:
    candidates: list[tuple[int, np.ndarray]] = []
    for semantic, accessor in attrs.items():
        if not isinstance(semantic, str) or not semantic.startswith("TEXCOORD_"):
            continue
        try:
            channel = int(semantic.split("_", 1)[1])
            if channels is not None and channel not in channels:
                continue
            values = _accessor_array(document, binary, int(accessor)).astype(np.float32, copy=False)
        except (ValueError, TypeError, GlbViewerError):
            continue
        if values.shape == (vertex_count, 2) and np.isfinite(values).all():
            candidates.append((channel, values))
    return sorted(candidates, key=lambda item: item[0])


def _select_livery_uv_channel(document: dict, binary: memoryview, attrs: dict, vertex_count: int, indices: np.ndarray, mask_pages: np.ndarray | None):
    """Select the UV stream with strongest exact vehicle-mask evidence.

    No fixed UV channel is required.  If multiple channels produce evidence,
    the channel covering the greatest number of actual non-zero vehicle-mask
    texels wins.  An exact tie prefers channel 3 because that is the published
    FH6/KFPS direct-livery semantic; remaining ties use stable channel order.
    """
    candidates = _uv_channel_candidates(document, binary, attrs, vertex_count)
    evidence = []
    for channel, values in candidates:
        bits, score, per_slot = _direct_uv_mask_evidence(values, indices, mask_pages)
        evidence.append((channel, values, bits, score, per_slot))
    positive = [item for item in evidence if item[2] and item[3] > 0]
    if not positive:
        return None, evidence
    positive.sort(key=lambda item: (-item[3], 0 if item[0] == 3 else 1, item[0]))
    return positive[0], evidence



_SLOT_GEOMETRY_SIDES = (0, 1, 2, 4, 3, 5, 6, 7, 8, 10, 9)

def _mask_bits_for_pixel_triangles(pixel: np.ndarray, mask_pages: np.ndarray, slots: list[int] | tuple[int, ...] | None = None) -> int:
    if pixel.ndim != 3 or pixel.shape[1:] != (3, 2) or not len(pixel):
        return 0
    pages = np.asarray(mask_pages)
    h, w = int(pages.shape[1]), int(pages.shape[2])
    min_xy = pixel.min(axis=1)
    max_xy = pixel.max(axis=1)
    intersects = (max_xy[:,0] >= 0.0) & (min_xy[:,0] <= w-1) & (max_xy[:,1] >= 0.0) & (min_xy[:,1] <= h-1)
    pixel = pixel[intersects]
    if not len(pixel):
        return 0
    x0=max(0,int(np.floor(pixel[:,:,0].min()))); y0=max(0,int(np.floor(pixel[:,:,1].min())))
    x1=min(w-1,int(np.ceil(pixel[:,:,0].max()))); y1=min(h-1,int(np.ceil(pixel[:,:,1].max())))
    if x1 < x0 or y1 < y0:
        return 0
    from PIL import Image, ImageDraw
    coverage_image=Image.new("1",(x1-x0+1,y1-y0+1),0)
    draw=ImageDraw.Draw(coverage_image)
    for triangle in pixel:
        points=[(float(px-x0),float(py-y0)) for px,py in triangle]
        draw.polygon(points,fill=1,outline=1)
        draw.line(points+[points[0]],fill=1,width=1)
    coverage=np.asarray(coverage_image,dtype=bool)
    if not np.any(coverage):
        return 0
    result=0
    scan=slots if slots is not None else range(11)
    for slot in scan:
        page,channel=divmod(int(slot),4)
        section=pages[page,y0:y1+1,x0:x1+1,channel] != 0
        if section.shape == coverage.shape and np.any(section & coverage):
            result |= 1 << int(slot)
    return result

def _projection_reference_bounds(reference_positions: np.ndarray, livery) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    minimum=np.zeros((11,2),dtype=np.float32)
    maximum=np.ones((11,2),dtype=np.float32)
    valid=np.zeros(11,dtype=np.float32)
    if livery is None or reference_positions.ndim != 2 or reference_positions.shape[1] != 3 or not len(reference_positions):
        return minimum,maximum,valid
    for slot in range(11):
        if not bool(livery.valid_slots[slot]):
            continue
        axis=np.asarray(livery.projection_axes[slot],dtype=np.float64)
        ax,ay=int(round(float(axis[0]))),int(round(float(axis[1])))
        sx,sy=float(axis[2]),float(axis[3])
        if ax not in (0,1,2) or ay not in (0,1,2) or sx == 0.0 or sy == 0.0:
            continue
        vx=reference_positions[:,ax].astype(np.float64)*sx
        vy=reference_positions[:,ay].astype(np.float64)*sy
        finite=np.isfinite(vx)&np.isfinite(vy)
        if not np.any(finite):
            continue
        lo=np.array([vx[finite].min(),vy[finite].min()],dtype=np.float64)
        hi=np.array([vx[finite].max(),vy[finite].max()],dtype=np.float64)
        if not np.all(np.isfinite(lo)) or not np.all(np.isfinite(hi)) or np.any(hi <= lo):
            continue
        minimum[slot]=lo.astype(np.float32); maximum[slot]=hi.astype(np.float32); valid[slot]=1.0
    return minimum,maximum,valid

def _projection_reference_bounds_by_slot(reference_by_slot: list[list[np.ndarray]], fallback_positions: np.ndarray, livery) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    minimum=np.zeros((11,2),dtype=np.float32)
    maximum=np.ones((11,2),dtype=np.float32)
    valid=np.zeros(11,dtype=np.float32)
    if livery is None:
        return minimum,maximum,valid
    for slot in range(11):
        rows=reference_by_slot[slot] if slot < len(reference_by_slot) else []
        values=np.concatenate(rows,axis=0) if rows else fallback_positions
        if values.ndim != 2 or values.shape[1] != 3 or not len(values):
            continue
        axis=np.asarray(livery.projection_axes[slot],dtype=np.float64)
        ax,ay=int(round(float(axis[0]))),int(round(float(axis[1])))
        sx,sy=float(axis[2]),float(axis[3])
        if ax not in (0,1,2) or ay not in (0,1,2) or sx == 0.0 or sy == 0.0:
            continue
        vx=values[:,ax].astype(np.float64)*sx; vy=values[:,ay].astype(np.float64)*sy
        finite=np.isfinite(vx)&np.isfinite(vy)
        if not np.any(finite):
            continue
        lo=np.array([vx[finite].min(),vy[finite].min()]); hi=np.array([vx[finite].max(),vy[finite].max()])
        if np.any(hi <= lo) or not np.all(np.isfinite(lo)) or not np.all(np.isfinite(hi)):
            continue
        minimum[slot]=lo.astype(np.float32); maximum[slot]=hi.astype(np.float32); valid[slot]=1.0
    return minimum,maximum,valid

def _infer_world_projection_mask(positions: np.ndarray, normals: np.ndarray, indices: np.ndarray, livery, projection_minimum: np.ndarray, projection_maximum: np.ndarray, projection_valid: np.ndarray) -> int:
    if livery is None:
        return 0
    pages=np.asarray(livery.mask_pages)
    if pages.shape != (3,1024,2048,4):
        return 0
    raw=np.asarray(indices,dtype=np.int64).reshape(-1)
    if len(raw)<3 or len(raw)%3 or int(raw.max(initial=0))>=len(positions):
        return 0
    tri=raw.reshape(-1,3)
    p=np.asarray(positions[tri],dtype=np.float64)
    n=np.asarray(normals[tri],dtype=np.float64) if normals.shape==positions.shape else np.zeros_like(p)
    finite=np.isfinite(p).all(axis=(1,2))
    p=p[finite]; n=n[finite]
    if not len(p):
        return 0
    # Average imported normals. If unavailable for a triangle, fall back to its geometric normal.
    navg=n.mean(axis=1)
    nlen=np.linalg.norm(navg,axis=1)
    bad=nlen == 0.0
    if np.any(bad):
        geo=np.cross(p[bad,1]-p[bad,0],p[bad,2]-p[bad,0])
        navg[bad]=geo
        nlen=np.linalg.norm(navg,axis=1)
    good=nlen > 0.0
    navg[good] /= nlen[good,None]
    result=0
    h,w=pages.shape[1],pages.shape[2]
    for slot in range(11):
        if not bool(livery.valid_slots[slot]) or projection_valid[slot] < 0.5:
            continue
        facing=np.asarray(livery.section_facings[slot],dtype=np.float64)
        facing_len=np.linalg.norm(facing)
        if facing_len == 0.0 or not np.isfinite(facing_len):
            continue
        facing=facing/facing_len
        front=good & ((navg @ facing) > 0.0)
        if not np.any(front):
            continue
        tp=p[front]
        axis=np.asarray(livery.projection_axes[slot],dtype=np.float64)
        ax,ay=int(round(float(axis[0]))),int(round(float(axis[1])))
        sx,sy=float(axis[2]),float(axis[3])
        lo=np.asarray(projection_minimum[slot],dtype=np.float64); hi=np.asarray(projection_maximum[slot],dtype=np.float64)
        span=hi-lo
        if ax not in (0,1,2) or ay not in (0,1,2) or np.any(span <= 0.0):
            continue
        xv=tp[:,:,ax]*sx; yv=tp[:,:,ay]*sy
        nx=(xv-lo[0])/span[0]; ny=(yv-lo[1])/span[1]
        region=np.asarray(livery.projection_mask_regions[slot],dtype=np.float64)
        au=region[0] + (region[1]-region[0])*nx
        av=region[2] + (region[3]-region[2])*ny
        pixel=np.stack((au*(w-1),av*(h-1)),axis=2)
        if _mask_bits_for_pixel_triangles(pixel,pages,[slot]) & (1<<slot):
            result |= 1 << slot
    return result


def load_kfps_glb(
    path: Path | str,
    livery=None,
    *,
    diagnostic_all_uv: bool = False,
    livery_uv_channel: int = 3,
    livery_eligibility: str = "legacy",
    neutral_cleanup_ab: bool = True,
    neutral_cleanup_c: bool = False,
) -> GlbSceneData:
    source = Path(path)
    try:
        livery_uv_channel = int(livery_uv_channel)
    except (TypeError, ValueError) as exc:
        raise GlbViewerError("Livery UV channel must be an integer from 0 through 3.") from exc
    if livery_uv_channel not in (0, 1, 2, 3):
        raise GlbViewerError(
            f"Unsupported livery UV channel TEXCOORD_{livery_uv_channel}; "
            "FH6 Assistant exposes TEXCOORD_0 through TEXCOORD_3."
        )
    livery_eligibility = normalize_livery_eligibility_policy(livery_eligibility)

    document, binary = _read_glb(source)
    mask_pages = livery.mask_pages if livery is not None else None
    meshes = document.get("meshes") or []
    materials = document.get("materials") or []
    if not meshes:
        raise GlbViewerError("GLB contains no meshes.")

    all_positions: list[np.ndarray] = []
    all_normals: list[np.ndarray] = []
    all_colors: list[np.ndarray] = []
    all_uv3: list[np.ndarray] = []
    all_allowed: list[np.ndarray] = []
    all_projection: list[np.ndarray] = []
    all_direct: list[np.ndarray] = []
    all_indices: list[np.ndarray] = []
    role_counts: dict[str, int] = {}
    vertex_base = 0
    included_meshes = 0
    uv3_meshes = 0
    projected_meshes = 0
    excluded_livery_meshes = 0
    inferred_uv3_meshes = 0
    promoted_livery_meshes = 0
    expanded_allowed_meshes = 0
    uv3_without_mask_overlap = 0
    inferred_projection_meshes = 0
    projection_no_overlap_meshes = 0
    selected_uv_channel_counts: dict[int, int] = {}
    alternate_uv_channel_primitives = 0
    uv_channel_candidates_without_overlap = 0
    selected_uv_mask_evidence_meshes = 0
    selected_uv_without_mask_overlap = 0
    primitive_diagnostics: list[dict] = []
    neutral_ab_excluded_meshes = 0
    neutral_c_excluded_meshes = 0

    # Neutral inspection palette. M3 validates geometry, not game paint materials.
    role_color = {
        "paint": np.array([0.72, 0.75, 0.78], dtype=np.float32),
        "glass": np.array([0.25, 0.43, 0.55], dtype=np.float32),
        "dark": np.array([0.10, 0.11, 0.12], dtype=np.float32),
        "trim": np.array([0.36, 0.38, 0.40], dtype=np.float32),
    }

    node_extras_by_mesh: dict[int, dict] = {}
    for node in document.get("nodes") or []:
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        try:
            mesh_index = int(node["mesh"])
        except (TypeError, ValueError):
            continue
        if 0 <= mesh_index < len(meshes):
            node_extras_by_mesh[mesh_index] = dict(node.get("extras") or {})

    # Projection reference construction is required only when a livery contract is
    # active. Neutral geometry inspection skips this second full-mesh pre-pass.
    if livery is None:
        projection_minimum = np.zeros((11, 2), dtype=np.float32)
        projection_maximum = np.ones((11, 2), dtype=np.float32)
        projection_valid = np.zeros(11, dtype=np.float32)
    else:
        projection_reference: list[np.ndarray] = []
        projection_fallback_reference: list[np.ndarray] = []
        projection_reference_by_slot: list[list[np.ndarray]] = [[] for _ in range(11)]
        for pre_mesh_index, pre_mesh in enumerate(meshes):
            pre_extras = dict(node_extras_by_mesh.get(pre_mesh_index) or {})
            pre_extras.update(pre_mesh.get("extras") or {})
            pre_excluded, _pre_exclusion_reason = _neutral_geometry_excluded(
                pre_extras, bool(neutral_cleanup_ab), bool(neutral_cleanup_c)
            )
            if pre_excluded:
                continue
            for pre_primitive in pre_mesh.get("primitives") or []:
                attrs = pre_primitive.get("attributes") or {}
                if "POSITION" not in attrs:
                    continue
                try:
                    pre_positions = _accessor_array(document, binary, int(attrs["POSITION"])).astype(np.float32, copy=False)
                except Exception:
                    continue
                if pre_positions.ndim != 2 or pre_positions.shape[1] != 3 or not np.isfinite(pre_positions).all():
                    continue
                projection_fallback_reference.append(pre_positions)
                try:
                    if "indices" in pre_primitive:
                        pre_indices = _accessor_array(document, binary, int(pre_primitive["indices"])).reshape(-1).astype(np.uint32)
                    else:
                        pre_indices = np.arange(len(pre_positions), dtype=np.uint32)
                    pre_candidates = _uv_channel_candidates(
                        document,
                        binary,
                        attrs,
                        len(pre_positions),
                        channels={3},
                    )
                    if not pre_candidates:
                        continue
                    _pre_channel, pre_render_uv = pre_candidates[0]
                    direct_bits, _score, _per_slot = _direct_uv_mask_evidence(
                        pre_render_uv, pre_indices, mask_pages
                    )
                except Exception:
                    continue
                if not direct_bits:
                    continue
                projection_reference.append(pre_positions)
                for pre_slot in range(11):
                    if direct_bits & (1 << pre_slot):
                        projection_reference_by_slot[pre_slot].append(pre_positions)
        reference_rows = projection_reference or projection_fallback_reference
        reference_positions = (
            np.concatenate(reference_rows, axis=0)
            if reference_rows else np.zeros((0, 3), dtype=np.float32)
        )
        projection_minimum, projection_maximum, projection_valid = _projection_reference_bounds_by_slot(
            projection_reference_by_slot, reference_positions, livery
        )

    for mesh_index, mesh in enumerate(meshes):
        extras = dict(node_extras_by_mesh.get(mesh_index) or {})
        extras.update(mesh.get("extras") or {})
        role = str(extras.get("kfps_role") or "trim").casefold()
        neutral_excluded, neutral_exclusion_reason = _neutral_geometry_excluded(
            extras, bool(neutral_cleanup_ab), bool(neutral_cleanup_c)
        )
        if neutral_excluded:
            if neutral_exclusion_reason == "neutral_ab":
                neutral_ab_excluded_meshes += 1
            elif neutral_exclusion_reason == "neutral_c":
                neutral_c_excluded_meshes += 1
            continue
        option_ids = extras.get("kfps_part_option_ids") or []
        if option_ids and extras.get("kfps_stock_part") is not True:
            # Match KFPS's initial stock-part visibility rule.
            continue
        primitives = mesh.get("primitives") or []
        for primitive_index, primitive in enumerate(primitives):
            if int(primitive.get("mode", 4)) != 4:
                continue
            attrs = primitive.get("attributes") or {}
            if "POSITION" not in attrs:
                continue
            positions = _accessor_array(document, binary, int(attrs["POSITION"])).astype(np.float32, copy=False)
            if positions.shape[1] != 3 or len(positions) == 0:
                continue
            if "NORMAL" in attrs:
                normals = _accessor_array(document, binary, int(attrs["NORMAL"])).astype(np.float32, copy=False)
                if normals.shape != positions.shape:
                    normals = np.zeros_like(positions)
                    normals[:, 1] = 1.0
            else:
                normals = np.zeros_like(positions)
                normals[:, 1] = 1.0
            if "indices" in primitive:
                indices = _accessor_array(document, binary, int(primitive["indices"])).reshape(-1).astype(np.uint32)
            else:
                indices = np.arange(len(positions), dtype=np.uint32)
            if len(indices) < 3:
                continue
            if int(indices.max(initial=0)) >= len(positions):
                raise GlbViewerError("A mesh contains an out-of-range vertex index.")

            color = role_color.get(role, role_color["trim"])
            colors = np.repeat(color[None, :], len(positions), axis=0)
            uv3 = np.zeros((len(positions), 2), dtype=np.float32)
            allowed_mask = 0
            projection_mask = 0
            direct_flag = 0.0
            raw_allowed = extras.get("kfps_allowed_sides")
            raw_projection = extras.get("kfps_projection_sides")
            declared_allowed = 0
            declared_projection = 0
            if role in {"paint", "glass"}:
                default_mask = 0x3F if role == "paint" else 0x7C0
                try:
                    declared_allowed = int(raw_allowed) if raw_allowed is not None else default_mask
                except (TypeError, ValueError):
                    declared_allowed = default_mask
                declared_allowed &= default_mask
                try:
                    declared_projection = int(raw_projection) if raw_projection is not None else 0
                except (TypeError, ValueError):
                    declared_projection = 0
                declared_projection &= default_mask
                allowed_mask = declared_allowed
                projection_mask = declared_projection

            # M6.24A rendering policy:
            #
            # Render coordinate:
            #   TEXCOORD_3 (default) or explicit TEXCOORD_0 diagnostic.
            #
            # Eligibility evidence remains independent from that render choice:
            #   legacy             = current M6.23 UV3/mask promotion/expansion
            #   strict             = converter-declared paint/glass only
            #   declared_confirmed = converter declaration INTERSECT UV3/mask evidence
            #
            # This isolation is deliberate: switching UV3 -> UV0 changes only the
            # coordinates used to sample the livery, not which primitives become
            # eligible because of a different UV channel.
            channels_to_read = None if diagnostic_all_uv else {3, livery_uv_channel}
            uv_candidates = _uv_channel_candidates(
                document,
                binary,
                attrs,
                len(positions),
                channels=channels_to_read,
            )
            uv_evidence = []
            for candidate_channel, candidate_values in uv_candidates:
                bits, score, per_slot = _direct_uv_mask_evidence(
                    candidate_values, indices, mask_pages
                )
                uv_evidence.append(
                    (candidate_channel, candidate_values, bits, score, per_slot)
                )

            uv3_entry = next((item for item in uv_evidence if item[0] == 3), None)
            selected_entry = next(
                (item for item in uv_evidence if item[0] == livery_uv_channel),
                None,
            )
            has_uv0 = "TEXCOORD_0" in attrs
            has_uv3 = "TEXCOORD_3" in attrs
            has_selected_uv = selected_entry is not None
            inferred_mask = 0  # UV3/mask eligibility evidence, preserves M6.23 semantics.
            selected_uv_mask = 0
            selected_uv_channel = None
            alternate_best_channel = None
            alternate_best_score = 0

            alternate_positive = [
                item
                for item in uv_evidence
                if item[0] != livery_uv_channel and item[2] and item[3] > 0
            ]
            if alternate_positive:
                alternate_positive.sort(key=lambda item: (-item[3], item[0]))
                alternate_best_channel = int(alternate_positive[0][0])
                alternate_best_score = int(alternate_positive[0][3])
                alternate_uv_channel_primitives += 1

            if uv3_entry is not None:
                (
                    _uv3_channel,
                    _uv3_values,
                    uv3_bits,
                    _uv3_score,
                    _uv3_per_slot,
                ) = uv3_entry
                inferred_mask = int(uv3_bits)
                if inferred_mask:
                    inferred_uv3_meshes += 1
                else:
                    # Preserve the historical M6.23 UV3 diagnostic count.
                    uv3_without_mask_overlap += 1

            if selected_entry is not None:
                (
                    _selected_channel,
                    selected_values,
                    selected_bits,
                    _selected_score,
                    _selected_per_slot,
                ) = selected_entry
                uv3 = selected_values
                selected_uv_mask = int(selected_bits)
                if selected_uv_mask:
                    selected_uv_mask_evidence_meshes += 1

            if livery_eligibility == "legacy":
                # Eligibility and section expansion are exactly the M6.23 UV3
                # policy. Only the coordinates used for direct rendering can be
                # switched to UV0.
                if inferred_mask:
                    if role not in {"paint", "glass"}:
                        promoted_livery_meshes += 1
                    elif inferred_mask & ~allowed_mask:
                        expanded_allowed_meshes += 1
                    allowed_mask |= inferred_mask

                eligible_direct = (
                    role in {"paint", "glass"}
                    or bool(inferred_mask)
                )
                if eligible_direct and selected_entry is not None:
                    direct_flag = 1.0
                    projection_mask = 0
                    selected_uv_channel = livery_uv_channel
                    if not selected_uv_mask:
                        selected_uv_without_mask_overlap += 1

            elif livery_eligibility == "strict":
                # Converter role/sides are authoritative. UV3 mask evidence may
                # be reported, but cannot promote or expand anything.
                if role not in {"paint", "glass"}:
                    allowed_mask = 0
                    projection_mask = 0
                elif selected_entry is not None:
                    direct_flag = 1.0
                    projection_mask = 0
                    selected_uv_channel = livery_uv_channel
                    if not selected_uv_mask:
                        selected_uv_without_mask_overlap += 1

            elif livery_eligibility == "declared_confirmed":
                # User-requested confirmation policy: the primitive/section must
                # be declared paint/glass AND have actual UV3/mask evidence.
                # The resulting confirmed primitive may then be rendered with
                # either UV3 or diagnostic UV0.
                projection_mask = 0
                if role in {"paint", "glass"} and inferred_mask:
                    confirmed_mask = int(declared_allowed) & int(inferred_mask)
                    if confirmed_mask and selected_entry is not None:
                        allowed_mask = confirmed_mask
                        direct_flag = 1.0
                        selected_uv_channel = livery_uv_channel
                        if not selected_uv_mask:
                            selected_uv_without_mask_overlap += 1
                    else:
                        allowed_mask = 0
                else:
                    allowed_mask = 0

            if selected_uv_channel is not None:
                selected_uv_channel_counts[selected_uv_channel] = (
                    selected_uv_channel_counts.get(selected_uv_channel, 0) + 1
                )
            elif selected_entry is None and uv_candidates:
                uv_channel_candidates_without_overlap += 1

            # Compute geometry-derived projection only as diagnostic evidence.  It is
            # intentionally NOT OR-ed into allowed_mask/projection_mask in M6.23.
            inferred_projection_slots = 0
            if diagnostic_all_uv and direct_flag <= 0.5 and livery is not None:
                inferred_projection_slots = _infer_world_projection_mask(
                    positions, normals, indices, livery, projection_minimum, projection_maximum, projection_valid
                )
                if inferred_projection_slots:
                    inferred_projection_meshes += 1
                else:
                    projection_no_overlap_meshes += 1

            if direct_flag > 0.5:
                uv3_meshes += 1
            elif role in {"paint", "glass"} and projection_mask:
                projected_meshes += 1
            elif role in {"paint", "glass"}:
                excluded_livery_meshes += 1
                allowed_mask = 0
            material_index = primitive.get("material")
            material_name = ""
            if isinstance(material_index, int) and 0 <= material_index < len(materials):
                material_name = str((materials[material_index] or {}).get("name") or "")
            primitive_diagnostics.append({
                "mesh_index": mesh_index,
                "mesh_name": str(mesh.get("name") or ""),
                "primitive_index": primitive_index,
                "material_index": material_index if isinstance(material_index, int) else None,
                "material_name": material_name,
                "source_entry": str(extras.get("kfps_source_entry") or ""),
                "part_type": str(extras.get("kfps_part_type") or ""),
                "instance_identity": str(extras.get("kfps_instance_identity") or ""),
                "declared_role": role,
                "neutral_ab_hidden": bool(extras.get("kfps_neutral_ab_hidden", False)),
                "neutral_ab_reasons": list(extras.get("kfps_neutral_ab_reasons") or []),
                "neutral_c_candidate": bool(extras.get("kfps_neutral_c_candidate", False)),
                "neutral_c_reasons": list(extras.get("kfps_neutral_c_reasons") or []),
                "has_uv0": bool(has_uv0),
                "has_uv3": bool(has_uv3),
                "has_selected_uv": bool(has_selected_uv),
                "requested_livery_uv_channel": int(livery_uv_channel),
                "eligibility_evidence_uv_channel": 3,
                "eligibility_policy": livery_eligibility,
                "available_uv_channels": [int(channel) for channel, _ in uv_candidates],
                "selected_livery_uv_channel": int(selected_uv_channel) if selected_uv_channel is not None else None,
                "alternate_uv_diagnostic_channel": alternate_best_channel,
                "alternate_uv_diagnostic_texels": alternate_best_score,
                "uv_channel_evidence": {
                    str(channel): {"section_bits": int(bits), "intersected_mask_texels": int(score), "per_slot_texels": [int(v) for v in per_slot]}
                    for channel, _values, bits, score, per_slot in uv_evidence
                },
                "declared_allowed_sides": declared_allowed,
                "uv3_evidence_sides": inferred_mask,
                "selected_uv_evidence_sides": selected_uv_mask,
                "inferred_mask_sides": inferred_mask,
                "final_allowed_sides": allowed_mask,
                "projection_sides": projection_mask,
                "inferred_projection_slots": inferred_projection_slots,
                "direct_uv": bool(direct_flag > 0.5),
                "mask_inference_method": (
                    f"eligibility_uv3_render_uv{livery_uv_channel}_plus_all_uv_diagnostic"
                    if diagnostic_all_uv and uv_candidates
                    else f"eligibility_uv3_render_uv{livery_uv_channel}"
                    if uv_candidates
                    else "none"
                ),
                "inference_action": (
                    "promoted_by_vehicle_mask"
                    if (
                        livery_eligibility == "legacy"
                        and inferred_mask
                        and role not in {"paint", "glass"}
                    )
                    else "expanded_by_vehicle_mask"
                    if (
                        livery_eligibility == "legacy"
                        and role in {"paint", "glass"}
                        and inferred_mask & ~declared_allowed
                    )
                    else "declared_confirmed"
                    if (
                        livery_eligibility == "declared_confirmed"
                        and direct_flag > 0.5
                    )
                    else "strict_declared_direct"
                    if (
                        livery_eligibility == "strict"
                        and direct_flag > 0.5
                    )
                    else "declared_direct"
                    if direct_flag > 0.5
                    else "projection_diagnostic_only"
                    if inferred_projection_slots
                    else "projection"
                    if projection_mask
                    else "none"
                ),
                "triangle_count": int(len(indices) // 3),
            })
            allowed = np.full((len(positions), 1), float(allowed_mask), dtype=np.float32)
            projection = np.full((len(positions), 1), float(projection_mask), dtype=np.float32)
            direct = np.full((len(positions), 1), direct_flag, dtype=np.float32)
            all_positions.append(positions)
            all_normals.append(normals)
            all_colors.append(colors)
            all_uv3.append(uv3)
            all_allowed.append(allowed)
            all_projection.append(projection)
            all_direct.append(direct)
            all_indices.append(indices + np.uint32(vertex_base))
            vertex_base += len(positions)
            included_meshes += 1
            role_counts[role] = role_counts.get(role, 0) + 1

    if not all_positions:
        raise GlbViewerError("No visible triangle geometry was found in the GLB.")
    positions = np.ascontiguousarray(np.concatenate(all_positions), dtype=np.float32)
    normals = np.ascontiguousarray(np.concatenate(all_normals), dtype=np.float32)
    colors = np.ascontiguousarray(np.concatenate(all_colors), dtype=np.float32)
    uv3 = np.ascontiguousarray(np.concatenate(all_uv3), dtype=np.float32)
    allowed_sides = np.ascontiguousarray(np.concatenate(all_allowed), dtype=np.float32)
    projection_sides = np.ascontiguousarray(np.concatenate(all_projection), dtype=np.float32)
    direct_uv = np.ascontiguousarray(np.concatenate(all_direct), dtype=np.float32)
    indices = np.ascontiguousarray(np.concatenate(all_indices), dtype=np.uint32)
    if not np.isfinite(positions).all() or not np.isfinite(normals).all():
        raise GlbViewerError("GLB contains non-finite geometry values.")
    return GlbSceneData(
        positions=positions,
        normals=normals,
        colors=colors,
        uv3=uv3,
        allowed_sides=allowed_sides,
        projection_sides=projection_sides,
        direct_uv=direct_uv,
        indices=indices,
        mesh_count=included_meshes,
        triangle_count=len(indices) // 3,
        role_counts=role_counts,
        uv3_meshes=uv3_meshes,
        projected_meshes=projected_meshes,
        excluded_livery_meshes=excluded_livery_meshes,
        inferred_uv3_meshes=inferred_uv3_meshes,
        promoted_livery_meshes=promoted_livery_meshes,
        expanded_allowed_meshes=expanded_allowed_meshes,
        uv3_without_mask_overlap=uv3_without_mask_overlap,
        inferred_projection_meshes=inferred_projection_meshes,
        projection_no_overlap_meshes=projection_no_overlap_meshes,
        selected_uv_channel_counts=dict(sorted(selected_uv_channel_counts.items())),
        alternate_uv_channel_primitives=alternate_uv_channel_primitives,
        uv_channel_candidates_without_overlap=uv_channel_candidates_without_overlap,
        selected_uv_mask_evidence_meshes=selected_uv_mask_evidence_meshes,
        selected_uv_without_mask_overlap=selected_uv_without_mask_overlap,
        projection_minimum=np.ascontiguousarray(projection_minimum),
        projection_maximum=np.ascontiguousarray(projection_maximum),
        projection_valid=np.ascontiguousarray(projection_valid),
        primitive_diagnostics=tuple(primitive_diagnostics),
        livery_uv_channel=int(livery_uv_channel),
        livery_eligibility_policy=livery_eligibility,
        neutral_cleanup_ab_enabled=bool(neutral_cleanup_ab),
        neutral_cleanup_c_enabled=bool(neutral_cleanup_c),
        neutral_ab_excluded_meshes=int(neutral_ab_excluded_meshes),
        neutral_c_excluded_meshes=int(neutral_c_excluded_meshes),
        bounds_min=positions.min(axis=0),
        bounds_max=positions.max(axis=0),
    )


