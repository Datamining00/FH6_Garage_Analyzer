from __future__ import annotations

from dataclasses import asdict, dataclass

from .modelbin_morph import (
    DXGI_R16G16B16A16_FLOAT,
    ModelbinMorphError,
    MorphBufferInfo,
    decode_half4_record,
)


@dataclass(frozen=True)
class WeightedMorphSelectorStats:
    selector: int
    record_count: int
    nonzero_record_count: int
    sum_abs_delta: tuple[float, float, float]
    mean_abs_delta: tuple[float, float, float]
    max_abs_delta: tuple[float, float, float]
    min_signed_delta: tuple[float, float, float]
    max_signed_delta: tuple[float, float, float]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WeightedMorphTargetProfile:
    morph_target_count: int
    buffer_blob_index: int
    buffer_identifier_id: int | None
    buffer_format: int
    buffer_stride: int
    declared_buffer_length: int
    profiled_vertex_count: int
    selectors: tuple[WeightedMorphSelectorStats, ...]
    missing_selectors: tuple[int, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def profile_weighted_morph_targets(
    buffer: MorphBufferInfo,
    morph_target_count: int,
) -> WeightedMorphTargetProfile:
    """Summarize HALF4 position deltas by the selector stored in each record.

    This is diagnostic-only. It deliberately reports axis statistics without
    assigning semantic labels such as diameter or width to any selector.
    Normal-delta records, when present later in the vertex stride, are ignored.
    """
    if morph_target_count <= 0:
        raise ModelbinMorphError("morph_target_count must be positive")
    if buffer.format != DXGI_R16G16B16A16_FLOAT:
        raise ModelbinMorphError(
            f"Weighted selector profiling is verified only for HALF4 format; got {buffer.format}"
        )
    if buffer.stride <= 0:
        raise ModelbinMorphError("Morph buffer stride must be positive")

    position_bytes = morph_target_count * 8
    if buffer.stride < position_bytes:
        raise ModelbinMorphError(
            f"Morph buffer stride {buffer.stride} is too short for "
            f"{morph_target_count} HALF4 position records"
        )

    available_vertices = len(buffer.raw_data) // buffer.stride
    if buffer.length > 0:
        vertex_count = min(buffer.length, available_vertices)
    else:
        vertex_count = available_vertices
    if vertex_count <= 0:
        raise ModelbinMorphError("Morph buffer contains no complete vertex records")

    accumulators: dict[int, dict[str, object]] = {}
    for vertex_index in range(vertex_count):
        vertex_base = vertex_index * buffer.stride
        for slot in range(morph_target_count):
            record = decode_half4_record(buffer.raw_data, vertex_base + slot * 8)
            selector = record.target_index
            if selector < 0 or selector >= morph_target_count:
                raise ModelbinMorphError(
                    f"Morph target selector {selector} is outside declared target count "
                    f"{morph_target_count}"
                )

            values = (record.dx, record.dy, record.dz)
            stats = accumulators.setdefault(
                selector,
                {
                    "record_count": 0,
                    "nonzero_record_count": 0,
                    "sum_abs_delta": [0.0, 0.0, 0.0],
                    "max_abs_delta": [0.0, 0.0, 0.0],
                    "min_signed_delta": [float("inf"), float("inf"), float("inf")],
                    "max_signed_delta": [float("-inf"), float("-inf"), float("-inf")],
                },
            )
            stats["record_count"] = int(stats["record_count"]) + 1
            if any(value != 0.0 for value in values):
                stats["nonzero_record_count"] = int(stats["nonzero_record_count"]) + 1

            sum_abs = stats["sum_abs_delta"]
            max_abs = stats["max_abs_delta"]
            min_signed = stats["min_signed_delta"]
            max_signed = stats["max_signed_delta"]
            assert isinstance(sum_abs, list)
            assert isinstance(max_abs, list)
            assert isinstance(min_signed, list)
            assert isinstance(max_signed, list)
            for axis, value in enumerate(values):
                absolute = abs(value)
                sum_abs[axis] += absolute
                if absolute > max_abs[axis]:
                    max_abs[axis] = absolute
                if value < min_signed[axis]:
                    min_signed[axis] = value
                if value > max_signed[axis]:
                    max_signed[axis] = value

    selectors: list[WeightedMorphSelectorStats] = []
    for selector in sorted(accumulators):
        stats = accumulators[selector]
        record_count = int(stats["record_count"])
        sum_abs = tuple(float(value) for value in stats["sum_abs_delta"])
        max_abs = tuple(float(value) for value in stats["max_abs_delta"])
        min_signed = tuple(float(value) for value in stats["min_signed_delta"])
        max_signed = tuple(float(value) for value in stats["max_signed_delta"])
        selectors.append(
            WeightedMorphSelectorStats(
                selector=selector,
                record_count=record_count,
                nonzero_record_count=int(stats["nonzero_record_count"]),
                sum_abs_delta=sum_abs,
                mean_abs_delta=tuple(value / record_count for value in sum_abs),
                max_abs_delta=max_abs,
                min_signed_delta=min_signed,
                max_signed_delta=max_signed,
            )
        )

    seen = set(accumulators)
    return WeightedMorphTargetProfile(
        morph_target_count=morph_target_count,
        buffer_blob_index=buffer.blob_index,
        buffer_identifier_id=buffer.identifier_id,
        buffer_format=buffer.format,
        buffer_stride=buffer.stride,
        declared_buffer_length=buffer.length,
        profiled_vertex_count=vertex_count,
        selectors=tuple(selectors),
        missing_selectors=tuple(selector for selector in range(morph_target_count) if selector not in seen),
    )
