from __future__ import annotations

import json
import struct
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any


class _GlbReadError(ValueError):
    pass


def _mesh_indices_with_native_tire_nodes(path: str | Path) -> set[int]:
    """Return mesh indices referenced by derived native-tire nodes in a GLB."""
    source = Path(path)
    data = source.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise _GlbReadError("not a GLB 2 container")
    version, total = struct.unpack_from("<II", data, 4)
    if version != 2 or total > len(data):
        raise _GlbReadError("invalid GLB header")
    json_len, json_kind = struct.unpack_from("<I4s", data, 12)
    if json_kind != b"JSON" or 20 + json_len > len(data):
        raise _GlbReadError("missing GLB JSON chunk")
    document = json.loads(data[20:20 + json_len].decode("utf-8").rstrip(" \t\r\n\x00"))
    result: set[int] = set()
    for node in document.get("nodes") or ():
        if not isinstance(node, dict):
            continue
        extras = node.get("extras") or {}
        if not isinstance(extras, dict) or extras.get("fh6_native_tire_trial") is not True:
            continue
        try:
            result.add(int(node["mesh"]))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def annotate_native_tire_visibility_provenance(scene: Any, path: str | Path) -> Any:
    """Annotate parser diagnostics so display filtering can identify merged tires."""
    try:
        native_meshes = _mesh_indices_with_native_tire_nodes(path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, struct.error):
        return scene
    if not native_meshes:
        return scene

    changed = False
    diagnostics = []
    for raw in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
        if not isinstance(raw, dict):
            diagnostics.append(raw)
            continue
        item = dict(raw)
        try:
            is_native = int(item.get("mesh_index", -1)) in native_meshes
        except (TypeError, ValueError):
            is_native = False
        if is_native:
            item["fh6_native_tire_trial"] = True
            changed = True
        diagnostics.append(item)
    if not changed:
        return scene
    return replace(scene, primitive_diagnostics=tuple(diagnostics))


def install_native_tire_visibility_provenance_patch() -> bool:
    """Wrap GLB parsing without modifying source/cached GLBs."""
    from . import glb_parser

    if getattr(glb_parser, "_fh6_native_tire_visibility_provenance_patched", False):
        return False
    original = glb_parser.load_kfps_glb

    def wrapped(path, *args, **kwargs):
        scene = original(path, *args, **kwargs)
        return annotate_native_tire_visibility_provenance(scene, path)

    glb_parser.load_kfps_glb = wrapped
    glb_parser._fh6_native_tire_visibility_provenance_patched = True

    integration = sys.modules.get(f"{__package__}.integration")
    if integration is not None and getattr(integration, "load_kfps_glb", None) is original:
        integration.load_kfps_glb = wrapped
    return True
