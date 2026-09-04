from __future__ import annotations

from .glb_parser import GlbSceneData


_TIRE_PART_TYPES = {
    "tirecompound",
    "ccarparts_tirecompound",
}


def native_wheel_scene_info(scene: GlbSceneData) -> dict:
    """Describe wheel/tire geometry already present in the converted carbin scene.

    M6.24B adds no procedural wheel or tire geometry. The pinned chassis
    converter serializes each carbin model instance into the cached GLB and
    preserves both ``kfps_source_entry`` and ``kfps_part_type`` in extras.

    Wheel resource-path matching is diagnostic only; it never changes renderer
    eligibility or visibility. Tire identification uses the structured carbin
    part type emitted by the converter, not a filename/material-name guess.
    """
    wheel_primitives = 0
    wheel_sources: set[str] = set()
    tire_primitives = 0
    tire_sources: set[str] = set()
    tire_part_types: set[str] = set()

    for item in scene.primitive_diagnostics:
        source = str(item.get("source_entry") or "").replace("\\", "/")
        normalized_source = "/" + source.casefold().strip("/") + "/"
        if "/wheels/" in normalized_source:
            wheel_primitives += 1
            if source:
                wheel_sources.add(source)

        part_type = str(item.get("part_type") or "").strip()
        normalized_part = part_type.casefold().replace(" ", "").replace("-", "").replace("_", "")
        is_tire = normalized_part in {
            value.replace("_", "") for value in _TIRE_PART_TYPES
        }
        if is_tire:
            tire_primitives += 1
            if source:
                tire_sources.add(source)
            if part_type:
                tire_part_types.add(part_type)

    return {
        "wheel_mode": "native_carbin_scene",
        "wheel_locator_count": 0,
        "native_wheel_primitives": wheel_primitives,
        "native_wheel_sources": tuple(sorted(wheel_sources, key=str.casefold)),
        "native_tire_primitives": tire_primitives,
        "native_tire_sources": tuple(sorted(tire_sources, key=str.casefold)),
        "native_tire_part_types": tuple(sorted(tire_part_types, key=str.casefold)),
        "placeholder_meshes_added": 0,
        "tire_resource_status": (
            "native_tirecompound_geometry_present"
            if tire_primitives
            else "no_visible_tirecompound_primitive_in_cached_glb"
        ),
    }
