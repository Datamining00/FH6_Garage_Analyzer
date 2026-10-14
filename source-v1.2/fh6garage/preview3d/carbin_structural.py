from __future__ import annotations

import struct
from dataclasses import dataclass


class CarbinStructuralError(ValueError):
    pass


# Public ForzaTech car-part enum values documented by ForzaTechStudio.
# These are file-format identifiers, not vehicle/model-specific rules.
PART_NAMES: dict[int, str] = {
    0: "CCarParts_Engine",
    1: "CCarParts_Drivetrain",
    2: "CCarParts_CarBody",
    3: "CCarParts_Motor",
    4: "CCarParts_Brakes",
    5: "CCarParts_SpringDamper",
    6: "CCarParts_AntiSwayFront",
    7: "CCarParts_AntiSwayRear",
    8: "CCarParts_TireCompound",
    9: "CCarParts_RearWing",
    10: "CCarParts_RimSizeFront",
    11: "CCarParts_RimSizeRear",
    34: "CCarParts_FrontBumper",
    35: "CCarParts_RearBumper",
    36: "CCarParts_Hood",
    37: "CCarParts_SideSkirts",
    38: "CCarParts_TireWidthFront",
    39: "CCarParts_TireWidthRear",
    40: "CCarParts_WeightReduction",
    41: "CCarParts_ChassisStiffness",
    42: "CCarParts_Ballast",
    43: "CCarParts_MotorParts",
    44: "CCarParts_WheelStyle",
    45: "CCarParts_Aspiration",
}

# The three format-level part types that can directly carry tire geometry.
TIRE_GEOMETRY_PART_TYPES = frozenset({8, 38, 39})
RIM_GEOMETRY_PART_TYPES = frozenset({10, 11, 44})

_MAX_COUNT = 100_000
_MAX_STRING = 10_000
_MAX_BLOB = 64 * 1024 * 1024


@dataclass
class _Reader:
    data: bytes
    offset: int = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def _take(self, size: int, context: str) -> bytes:
        if size < 0 or size > self.remaining():
            raise CarbinStructuralError(
                f"{context}: need {size} bytes at 0x{self.offset:X}, only {self.remaining()} remain"
            )
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def unpack(self, fmt: str, context: str):
        size = struct.calcsize(fmt)
        values = struct.unpack(fmt, self._take(size, context))
        return values[0] if len(values) == 1 else values

    def u8(self, context: str) -> int:
        return int(self.unpack("<B", context))

    def i8(self, context: str) -> int:
        return int(self.unpack("<b", context))

    def u16(self, context: str) -> int:
        return int(self.unpack("<H", context))

    def i16(self, context: str) -> int:
        return int(self.unpack("<h", context))

    def u32(self, context: str) -> int:
        return int(self.unpack("<I", context))

    def i32(self, context: str) -> int:
        return int(self.unpack("<i", context))

    def u64(self, context: str) -> int:
        return int(self.unpack("<Q", context))

    def f32(self, context: str) -> float:
        return float(self.unpack("<f", context))

    def guid_hex(self, context: str) -> str:
        return self._take(16, context).hex()

    def string(self, context: str) -> str:
        length = self.i32(f"{context} length")
        if length <= 0:
            return ""
        if length > _MAX_STRING:
            raise CarbinStructuralError(f"{context}: string length {length} exceeds {_MAX_STRING}")
        return self._take(length, context).decode("utf-8", errors="replace")

    def count(self, context: str) -> int:
        value = self.u32(context)
        if value > _MAX_COUNT:
            raise CarbinStructuralError(f"{context}: count {value} exceeds {_MAX_COUNT}")
        return value


def _enum_v1_to_latest(value: int) -> int:
    # ForzaTechStudio: FM2023 inserted Ballast at 42; pre-FM2023 enum V1 values
    # from 42 upward are shifted by one in the latest enum.
    return value + 1 if value >= 42 else value


def _part_name(value: int) -> str:
    if value in PART_NAMES:
        return PART_NAMES[value]
    if 12 <= value <= 33:
        return f"CCarParts_InternalUpgrade_{value}"
    return f"CCarParts_Unknown_{value}"


def _bounds(reader: _Reader, context: str) -> dict:
    values = [reader.f32(f"{context} value {i}") for i in range(8)]
    return {"min": values[:4], "max": values[4:]}


def _parse_model(reader: _Reader, scene_version: int, context: str) -> dict:
    model_version = reader.u16(f"{context} version")
    if model_version != 21:
        raise CarbinStructuralError(
            f"{context}: unsupported FH6 model version {model_version}; expected 21 for scene v7"
        )

    path = reader.string(f"{context} path")
    transform = [reader.f32(f"{context} transform[{i}]") for i in range(16)]
    lod_flags = reader.u16(f"{context} LOD flags")
    bone_name = reader.string(f"{context} bone name")
    bone_id = reader.i16(f"{context} bone id")
    snap_to_parent = bool(reader.u8(f"{context} snap to parent"))
    draw_groups = reader.u32(f"{context} draw groups")

    material_override_count = reader.count(f"{context} material override count")
    material_override_keys: list[str] = []
    for index in range(material_override_count):
        key = reader.string(f"{context} material override {index} key")
        value_length = reader.u32(f"{context} material override {index} length")
        if value_length > _MAX_BLOB:
            raise CarbinStructuralError(
                f"{context} material override {index}: value length {value_length} exceeds {_MAX_BLOB}"
            )
        reader._take(value_length, f"{context} material override {index} value")
        material_override_keys.append(key)

    material_index_count = reader.count(f"{context} material index count")
    material_indexes: list[dict] = []
    for index in range(material_index_count):
        key = reader.string(f"{context} material index {index} key")
        value = reader.u64(f"{context} material index {index} value")
        material_indexes.append({"key": key, "value": value, "value_hex": f"0x{value:016X}"})

    is_droppable = bool(reader.u8(f"{context} droppable"))
    drop_value = None
    drop_part_id = None
    if is_droppable:
        drop_value = reader.f32(f"{context} drop value")
        drop_part_id = reader.u32(f"{context} drop part id")

    break_amount = reader.f32(f"{context} break amount")

    ao_count = reader.count(f"{context} AO map count")
    ao_maps: list[dict] = []
    for index in range(ao_count):
        ao_version = reader.u16(f"{context} AO {index} version")
        ao_path = reader.string(f"{context} AO {index} path")
        ao_part_type = reader.u32(f"{context} AO {index} part type")
        ao_part_id = reader.i32(f"{context} AO {index} part id")
        ao: dict = {
            "version": ao_version,
            "path": ao_path,
            "part_type": ao_part_type,
            "part_id": ao_part_id,
        }
        if ao_version >= 2:
            ao["dropped_model_instance_guid"] = reader.guid_hex(f"{context} AO {index} dropped guid")
        else:
            ao["bone_index"] = reader.i16(f"{context} AO {index} bone index")
            ao["is_dropped"] = bool(reader.u8(f"{context} AO {index} is dropped"))
        ao["is_default"] = bool(reader.u8(f"{context} AO {index} default"))
        if ao_version >= 3:
            ao["lod_test"] = reader.i8(f"{context} AO {index} lod test")
            ao["lod_value"] = reader.i8(f"{context} AO {index} lod value")
        ao_maps.append(ao)

    is_interior_windshield = bool(reader.u8(f"{context} interior windshield"))
    receives_impact_mask = bool(reader.u8(f"{context} impact mask"))
    receives_splatter_mask = bool(reader.u8(f"{context} splatter mask"))
    receives_damage = bool(reader.u32(f"{context} receives damage"))
    receives_dirt = bool(reader.u32(f"{context} receives dirt"))
    receives_oil = bool(reader.u32(f"{context} receives oil"))
    receives_rubber = bool(reader.u32(f"{context} receives rubber"))

    assembly_name = reader.string(f"{context} assembly name")
    guid_v13 = reader.guid_hex(f"{context} guid v13")
    drop_guid_v14 = reader.guid_hex(f"{context} drop guid v14")
    ao_map_info_id_v14 = reader.u32(f"{context} AO map info id v14")
    horizon_unk_v15 = reader.i32(f"{context} horizon v15")

    damage_guid_count = reader.count(f"{context} damage guid count")
    damage_guids = [reader.guid_hex(f"{context} damage guid {i}") for i in range(damage_guid_count)]

    horizon_id = reader.u8(f"{context} horizon id")
    horizon_unk_v18 = reader.u32(f"{context} horizon v18")
    horizon_unk_v21_flag = reader.u32(f"{context} horizon v21 flag")
    horizon_unk_v21_path = reader.string(f"{context} horizon v21 path")

    return {
        "model_version": model_version,
        "resource_path": path,
        "transform_matrix_row_major": transform,
        "lod_flags": lod_flags,
        "bone_name": bone_name,
        "bone_id": bone_id,
        "snap_to_parent": snap_to_parent,
        "draw_groups_raw": draw_groups,
        "draw_groups": {
            "exterior": bool(draw_groups & 0x01),
            "cockpit": bool(draw_groups & 0x02),
            "shadow": bool(draw_groups & 0x04),
            "hood": bool(draw_groups & 0x08),
            "windshield_reflection": bool(draw_groups & 0x10),
            "driverless_cockpit": bool(draw_groups & 0x20),
            "windshield_reflection_driverless": bool(draw_groups & 0x40),
            "proxy_lod": bool(draw_groups & 0x80),
        },
        "material_override_count": material_override_count,
        "material_override_keys": material_override_keys,
        "material_index_count": material_index_count,
        "material_indexes": material_indexes,
        "is_droppable": is_droppable,
        "drop_value": drop_value,
        "drop_part_id": drop_part_id,
        "break_amount": break_amount,
        "ao_map_info_count": ao_count,
        "ao_map_infos": ao_maps,
        "is_interior_windshield": is_interior_windshield,
        "receives_impact_mask": receives_impact_mask,
        "receives_splatter_mask": receives_splatter_mask,
        "receives_damage": receives_damage,
        "receives_dirt": receives_dirt,
        "receives_oil": receives_oil,
        "receives_rubber": receives_rubber,
        "assembly_name": assembly_name,
        "guid_v13": guid_v13,
        "drop_guid_v14": drop_guid_v14,
        "ao_map_info_id_v14": ao_map_info_id_v14,
        "horizon_unk_v15": horizon_unk_v15,
        "damage_guid_count": damage_guid_count,
        "damage_guids": damage_guids,
        "horizon_id": horizon_id,
        "horizon_unk_v18": horizon_unk_v18,
        "horizon_unk_v21_flag": horizon_unk_v21_flag,
        "horizon_unk_v21_path": horizon_unk_v21_path,
    }


def _part_header(raw_type: int, prefix_type: int | None, kind: str, index: int, version: int) -> dict:
    resolved = _enum_v1_to_latest(raw_type)
    prefix_resolved = _enum_v1_to_latest(prefix_type) if prefix_type is not None else None
    return {
        "kind": kind,
        "part_index": index,
        "part_version": version,
        "prefix_part_type_raw": prefix_type,
        "prefix_part_type_resolved": prefix_resolved,
        "prefix_matches_payload": prefix_resolved is None or prefix_resolved == resolved,
        "raw_part_type": raw_type,
        "resolved_part_type": resolved,
        "resolved_part_type_name": _part_name(resolved),
        "is_tire_geometry_part": resolved in TIRE_GEOMETRY_PART_TYPES,
        "is_rim_geometry_part": resolved in RIM_GEOMETRY_PART_TYPES,
    }


def parse_fh6_carbin(data: bytes) -> dict:
    """Parse the FH6 scene-v7 numeric part graph without filename-based classification.

    The layout follows the public ForzaTechStudio carbin parser at commit
    4f373c5fb192551ce5249e320dd79b1399b693ca. This routine is diagnostic only;
    it does not assemble or filter production geometry.
    """
    reader = _Reader(bytes(data))
    scene_version = reader.u16("scene version")
    if scene_version != 7:
        raise CarbinStructuralError(
            f"unsupported scene version {scene_version}; this FH6 diagnostic expects scene v7"
        )

    build_guid = reader.guid_hex("build guid")
    build_strict = bool(reader.u8("build strict"))
    ordinal = reader.u32("ordinal")
    media_name = reader.string("media name")
    skeleton_path = reader.string("skeleton path")
    lod_flags = reader.u16("scene LOD flags")

    standard_parts: list[dict] = []
    standard_count = reader.count("non-upgradable parts count")
    for part_index in range(standard_count):
        prefix_type = reader.u8(f"standard part {part_index} prefix type")
        part_version = reader.u16(f"standard part {part_index} version")
        raw_type = reader.u32(f"standard part {part_index} type")
        item = _part_header(raw_type, prefix_type, "standard", part_index, part_version)
        model_count = reader.count(f"standard part {part_index} model count")
        item["model_count"] = model_count
        item["models"] = [
            _parse_model(reader, scene_version, f"standard part {part_index} model {model_index}")
            for model_index in range(model_count)
        ]
        if part_version >= 2:
            item["bounds"] = _bounds(reader, f"standard part {part_index} bounds")
        standard_parts.append(item)

    upgradable_parts: list[dict] = []
    upgradable_count = reader.count("upgradable parts count")
    for part_index in range(upgradable_count):
        part_version = reader.u16(f"upgradable part {part_index} version")
        raw_type = reader.u32(f"upgradable part {part_index} type")
        item = _part_header(raw_type, None, "upgradable", part_index, part_version)

        upgrades_count = reader.count(f"upgradable part {part_index} upgrades count")
        upgrades: list[dict] = []
        for upgrade_index in range(upgrades_count):
            upgrade_version = reader.u16(f"upgrade {part_index}/{upgrade_index} version")
            upgrade = {
                "version": upgrade_version,
                "level": reader.u8(f"upgrade {part_index}/{upgrade_index} level"),
                "is_stock": bool(reader.u8(f"upgrade {part_index}/{upgrade_index} is stock")),
                "part_id": reader.i32(f"upgrade {part_index}/{upgrade_index} part id"),
                "car_body_id": reader.i32(f"upgrade {part_index}/{upgrade_index} car body id"),
                "parent_is_stock": bool(reader.u8(f"upgrade {part_index}/{upgrade_index} parent stock")),
            }
            if upgrade_version < 3:
                legacy_model_count = reader.count(f"upgrade {part_index}/{upgrade_index} legacy model count")
                upgrade["legacy_models"] = [
                    _parse_model(reader, scene_version, f"upgrade {part_index}/{upgrade_index} model {i}")
                    for i in range(legacy_model_count)
                ]
            if upgrade_version >= 2:
                upgrade["bounds"] = _bounds(reader, f"upgrade {part_index}/{upgrade_index} bounds")
            upgrades.append(upgrade)
        item["upgrades"] = upgrades

        shared_models: list[dict] = []
        if part_version >= 3:
            shared_count = reader.count(f"upgradable part {part_index} shared model count")
            for model_index in range(shared_count):
                upgrade_id_count = reader.count(
                    f"upgradable part {part_index} shared model {model_index} upgrade id count"
                )
                upgrade_ids = [
                    reader.i32(f"upgradable part {part_index} shared model {model_index} upgrade id {i}")
                    for i in range(upgrade_id_count)
                ]
                model = _parse_model(
                    reader, scene_version, f"upgradable part {part_index} shared model {model_index}"
                )
                shared_models.append({"upgrade_ids": upgrade_ids, "model": model})
        item["shared_model_count"] = len(shared_models)
        item["shared_models"] = shared_models
        upgradable_parts.append(item)

    trailer: dict[str, object] = {}
    if reader.remaining() > 0:
        trailer["scene_unk_v6"] = bool(reader.u8("scene trailer v6"))
    if reader.remaining() > 0:
        trailer["scene_unk_v7"] = bool(reader.u8("scene trailer v7"))
    trailer["remaining_bytes"] = reader.remaining()
    if reader.remaining():
        trailer["remaining_hex"] = reader._take(reader.remaining(), "scene trailing bytes").hex()

    all_parts = standard_parts + upgradable_parts
    tire_related = [part for part in all_parts if part["resolved_part_type"] in TIRE_GEOMETRY_PART_TYPES]
    rim_related = [part for part in all_parts if part["resolved_part_type"] in RIM_GEOMETRY_PART_TYPES]

    return {
        "parser": "fh6_structural_carbin_v1",
        "reference": {
            "project": "D3FEKT/ForzaTechStudio",
            "commit": "4f373c5fb192551ce5249e320dd79b1399b693ca",
            "license": "MIT",
            "classification_basis": "numeric CCarParts enum and serialized carbin graph",
            "vehicle_name_matching_used": False,
            "resource_filename_matching_used_for_part_classification": False,
        },
        "scene": {
            "scene_version": scene_version,
            "expected_game": "Forza Horizon 6",
            "model_version_expected": 21,
            "build_guid_hex": build_guid,
            "build_strict": build_strict,
            "ordinal": ordinal,
            "media_name": media_name,
            "skeleton_path": skeleton_path,
            "lod_flags": lod_flags,
        },
        "standard_part_count": len(standard_parts),
        "standard_parts": standard_parts,
        "upgradable_part_count": len(upgradable_parts),
        "upgradable_parts": upgradable_parts,
        "tire_geometry_part_type_values": sorted(TIRE_GEOMETRY_PART_TYPES),
        "tire_related_part_count": len(tire_related),
        "tire_related_parts": tire_related,
        "rim_related_part_count": len(rim_related),
        "rim_related_parts": rim_related,
        "trailer": trailer,
    }
