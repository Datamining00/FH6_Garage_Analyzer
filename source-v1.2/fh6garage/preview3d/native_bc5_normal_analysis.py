from __future__ import annotations

"""Read-only BC5_UNORM payload analysis for native normal-map validation.

This module is diagnostic only. It does not enable normal-map rendering and it
does not assert that the common tangent-space BC5 convention is the FH6 shader
contract. The R->X, G->Y, positive-Z reconstruction is evaluated explicitly as
a hypothesis so real decoded FH6 payloads can be checked before shader wiring.
"""

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any

from .native_dds import NativeDdsError, native_dds_mip_bytes, parse_native_dds

NATIVE_BC5_NORMAL_ANALYSIS_REVISION = 1
_BC5_UNORM_DXGI = 83


class NativeBc5NormalAnalysisError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeBc5NormalAnalysis:
    revision: int
    status: str
    dds_path: str
    width: int
    height: int
    mip_levels: int
    pixel_count: int
    dxgi_format: int
    compression_family: str
    red_unorm_min: float
    red_unorm_max: float
    red_unorm_mean: float
    green_unorm_min: float
    green_unorm_max: float
    green_unorm_mean: float
    x_signed_min: float
    x_signed_max: float
    x_signed_mean: float
    x_signed_rms: float
    y_signed_min: float
    y_signed_max: float
    y_signed_mean: float
    y_signed_rms: float
    xy_length_mean: float
    xy_outside_unit_disk_count: int
    xy_outside_unit_disk_fraction: float
    reconstructed_positive_z_min: float
    reconstructed_positive_z_max: float
    reconstructed_positive_z_mean: float
    assumed_channel_mapping: str
    reconstruction_hypothesis: str
    y_orientation_status: str
    hypothesis_only: bool = True
    rendering_enabled: bool = False
    game_data_modified: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bc4_unorm_palette(block: bytes) -> tuple[float, ...]:
    if len(block) != 8:
        raise NativeBc5NormalAnalysisError(
            f"BC4 sub-block must be exactly 8 bytes, got {len(block)}."
        )
    endpoint0 = int(block[0])
    endpoint1 = int(block[1])
    if endpoint0 > endpoint1:
        raw = (
            float(endpoint0),
            float(endpoint1),
            (6.0 * endpoint0 + endpoint1) / 7.0,
            (5.0 * endpoint0 + 2.0 * endpoint1) / 7.0,
            (4.0 * endpoint0 + 3.0 * endpoint1) / 7.0,
            (3.0 * endpoint0 + 4.0 * endpoint1) / 7.0,
            (2.0 * endpoint0 + 5.0 * endpoint1) / 7.0,
            (endpoint0 + 6.0 * endpoint1) / 7.0,
        )
    else:
        raw = (
            float(endpoint0),
            float(endpoint1),
            (4.0 * endpoint0 + endpoint1) / 5.0,
            (3.0 * endpoint0 + 2.0 * endpoint1) / 5.0,
            (2.0 * endpoint0 + 3.0 * endpoint1) / 5.0,
            (endpoint0 + 4.0 * endpoint1) / 5.0,
            0.0,
            255.0,
        )
    return tuple(value / 255.0 for value in raw)


def _decode_bc4_unorm_block(block: bytes) -> tuple[float, ...]:
    palette = _bc4_unorm_palette(block)
    indices = int.from_bytes(block[2:8], "little", signed=False)
    return tuple(palette[(indices >> (3 * index)) & 0x7] for index in range(16))


def analyze_bc5_unorm_normal_dds(path: str | Path) -> NativeBc5NormalAnalysis:
    """Evaluate mip 0 under the standard BC5 tangent-normal hypothesis.

    The full first mip is decoded. No source or derivative file is modified.
    Y orientation intentionally remains unresolved because payload statistics
    alone cannot distinguish Direct3D-style and OpenGL-style tangent-space Y.
    """
    try:
        texture = parse_native_dds(path)
    except (OSError, NativeDdsError) as exc:
        raise NativeBc5NormalAnalysisError(str(exc)) from exc

    if not texture.is_simple_2d:
        raise NativeBc5NormalAnalysisError(
            "BC5 normal analysis accepts ordinary 2D DDS textures only."
        )
    if int(texture.dxgi_format) != _BC5_UNORM_DXGI:
        raise NativeBc5NormalAnalysisError(
            f"BC5 normal analysis requires DXGI 83 (BC5_UNORM), got {texture.dxgi_format}."
        )
    if str(texture.compression_family).casefold() != "bc5" or bool(texture.is_srgb):
        raise NativeBc5NormalAnalysisError(
            "DDS metadata is not the expected linear unsigned BC5 contract."
        )

    payload = native_dds_mip_bytes(texture, 0)
    blocks_wide = max(1, (int(texture.width) + 3) // 4)
    blocks_high = max(1, (int(texture.height) + 3) // 4)
    expected_size = blocks_wide * blocks_high * 16
    if len(payload) != expected_size:
        raise NativeBc5NormalAnalysisError(
            f"BC5 mip-0 payload size mismatch: expected {expected_size}, got {len(payload)}."
        )

    red_min = 1.0
    red_max = 0.0
    green_min = 1.0
    green_max = 0.0
    x_min = 1.0
    x_max = -1.0
    y_min = 1.0
    y_max = -1.0
    z_min = 1.0
    z_max = 0.0
    red_sum = 0.0
    green_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    x_sq_sum = 0.0
    y_sq_sum = 0.0
    xy_length_sum = 0.0
    z_sum = 0.0
    outside_count = 0
    pixel_count = 0

    for block_y in range(blocks_high):
        for block_x in range(blocks_wide):
            block_index = block_y * blocks_wide + block_x
            offset = block_index * 16
            red = _decode_bc4_unorm_block(payload[offset : offset + 8])
            green = _decode_bc4_unorm_block(payload[offset + 8 : offset + 16])
            for local_index in range(16):
                local_x = local_index & 3
                local_y = local_index >> 2
                pixel_x = block_x * 4 + local_x
                pixel_y = block_y * 4 + local_y
                if pixel_x >= texture.width or pixel_y >= texture.height:
                    continue

                r = float(red[local_index])
                g = float(green[local_index])
                x = r * 2.0 - 1.0
                y = g * 2.0 - 1.0
                xy_sq = x * x + y * y
                xy_length = math.sqrt(max(0.0, xy_sq))
                if xy_sq > 1.0 + 1e-12:
                    outside_count += 1
                z = math.sqrt(max(0.0, 1.0 - xy_sq))

                red_min = min(red_min, r)
                red_max = max(red_max, r)
                green_min = min(green_min, g)
                green_max = max(green_max, g)
                x_min = min(x_min, x)
                x_max = max(x_max, x)
                y_min = min(y_min, y)
                y_max = max(y_max, y)
                z_min = min(z_min, z)
                z_max = max(z_max, z)
                red_sum += r
                green_sum += g
                x_sum += x
                y_sum += y
                x_sq_sum += x * x
                y_sq_sum += y * y
                xy_length_sum += xy_length
                z_sum += z
                pixel_count += 1

    expected_pixels = int(texture.width) * int(texture.height)
    if pixel_count != expected_pixels or pixel_count <= 0:
        raise NativeBc5NormalAnalysisError(
            f"BC5 decoded pixel count mismatch: expected {expected_pixels}, got {pixel_count}."
        )

    count = float(pixel_count)
    return NativeBc5NormalAnalysis(
        revision=NATIVE_BC5_NORMAL_ANALYSIS_REVISION,
        status="bc5_unorm_xy_hypothesis_evaluated",
        dds_path=str(Path(texture.path).resolve()),
        width=int(texture.width),
        height=int(texture.height),
        mip_levels=int(texture.mip_levels),
        pixel_count=pixel_count,
        dxgi_format=int(texture.dxgi_format),
        compression_family=str(texture.compression_family),
        red_unorm_min=red_min,
        red_unorm_max=red_max,
        red_unorm_mean=red_sum / count,
        green_unorm_min=green_min,
        green_unorm_max=green_max,
        green_unorm_mean=green_sum / count,
        x_signed_min=x_min,
        x_signed_max=x_max,
        x_signed_mean=x_sum / count,
        x_signed_rms=math.sqrt(x_sq_sum / count),
        y_signed_min=y_min,
        y_signed_max=y_max,
        y_signed_mean=y_sum / count,
        y_signed_rms=math.sqrt(y_sq_sum / count),
        xy_length_mean=xy_length_sum / count,
        xy_outside_unit_disk_count=outside_count,
        xy_outside_unit_disk_fraction=outside_count / count,
        reconstructed_positive_z_min=z_min,
        reconstructed_positive_z_max=z_max,
        reconstructed_positive_z_mean=z_sum / count,
        assumed_channel_mapping="BC5 R->X, G->Y under standard tangent-space UNORM hypothesis",
        reconstruction_hypothesis="Z=+sqrt(max(0, 1-X^2-Y^2))",
        y_orientation_status="undetermined_requires_geometry_or_authoritative_reference",
    )


__all__ = [
    "NATIVE_BC5_NORMAL_ANALYSIS_REVISION",
    "NativeBc5NormalAnalysis",
    "NativeBc5NormalAnalysisError",
    "analyze_bc5_unorm_normal_dds",
]
