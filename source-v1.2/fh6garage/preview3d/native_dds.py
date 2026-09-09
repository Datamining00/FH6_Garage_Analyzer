from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

DDS_DX10_HEADER_SIZE = 148
_DDS_MAGIC = b"DDS "
_DX10_FOURCC = b"DX10"


class NativeDdsError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeDdsMip:
    level: int
    width: int
    height: int
    offset: int
    size: int


@dataclass(frozen=True)
class NativeDdsTexture:
    path: str
    width: int
    height: int
    depth: int
    mip_levels: int
    dxgi_format: int
    resource_dimension: int
    misc_flag: int
    array_size: int
    misc_flags2: int
    is_cube: bool
    is_srgb: bool
    compression_family: str
    block_bytes: int | None
    bits_per_pixel: int | None
    data_offset: int
    data_size: int
    mips: tuple[NativeDdsMip, ...]

    @property
    def is_simple_2d(self) -> bool:
        return (
            self.resource_dimension == 3
            and self.array_size == 1
            and not self.is_cube
            and self.depth <= 1
        )


# DXGI formats emitted by NativeSwatchbinDecoder.cs / ForzaTechStudio's
# SwatchbinService.  Format semantics are kept explicit and closed rather than
# treating unknown formats as 32-bpp data.
_BLOCK_FORMATS: dict[int, tuple[str, int, bool]] = {
    71: ("bc1", 8, False),
    72: ("bc1", 8, True),
    74: ("bc2", 16, False),
    75: ("bc2", 16, True),
    77: ("bc3", 16, False),
    78: ("bc3", 16, True),
    80: ("bc4", 8, False),
    81: ("bc4_snorm", 8, False),
    83: ("bc5", 16, False),
    84: ("bc5_snorm", 16, False),
    95: ("bc6h_uf16", 16, False),
    96: ("bc6h_sf16", 16, False),
    98: ("bc7", 16, False),
    99: ("bc7", 16, True),
}

_LINEAR_FORMATS: dict[int, tuple[str, int, bool]] = {
    2: ("rgba32f", 128, False),
    10: ("rgba16f", 64, False),
    11: ("rgba16_unorm", 64, False),
    28: ("rgba8", 32, False),
    29: ("rgba8", 32, True),
    49: ("rg8", 16, False),
    61: ("r8", 8, False),
    65: ("a8", 8, False),
    85: ("b5g6r5", 16, False),
    86: ("b5g5r5a1", 16, False),
    87: ("bgra8", 32, False),
}


def _mip_size(width: int, height: int, dxgi_format: int) -> int:
    block = _BLOCK_FORMATS.get(dxgi_format)
    if block is not None:
        _family, block_bytes, _srgb = block
        blocks_wide = max(1, (width + 3) // 4)
        blocks_high = max(1, (height + 3) // 4)
        return blocks_wide * blocks_high * block_bytes
    linear = _LINEAR_FORMATS.get(dxgi_format)
    if linear is not None:
        _family, bits_per_pixel, _srgb = linear
        return ((width * bits_per_pixel + 7) // 8) * height
    raise NativeDdsError(f"Unsupported native DDS DXGI format: {dxgi_format}")


def parse_native_dds(path: str | Path) -> NativeDdsTexture:
    source = Path(path).expanduser().resolve()
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise NativeDdsError(f"Could not read native DDS derivative: {source}: {exc}") from exc

    if len(data) < DDS_DX10_HEADER_SIZE:
        raise NativeDdsError(
            f"DDS derivative is truncated: {len(data)} bytes, expected at least {DDS_DX10_HEADER_SIZE}."
        )
    if data[:4] != _DDS_MAGIC:
        raise NativeDdsError("DDS derivative is missing the DDS magic.")

    header_size = struct.unpack_from("<I", data, 4)[0]
    pixel_format_size = struct.unpack_from("<I", data, 76)[0]
    fourcc = data[84:88]
    if header_size != 124 or pixel_format_size != 32 or fourcc != _DX10_FOURCC:
        raise NativeDdsError(
            "DDS derivative is not the expected DDS_HEADER + DX10 container."
        )

    height = int(struct.unpack_from("<I", data, 12)[0])
    width = int(struct.unpack_from("<I", data, 16)[0])
    depth = int(struct.unpack_from("<I", data, 24)[0])
    mip_levels = int(struct.unpack_from("<I", data, 28)[0])
    dxgi_format, resource_dimension, misc_flag, array_size, misc_flags2 = struct.unpack_from(
        "<IIIII", data, 128
    )

    if width <= 0 or height <= 0:
        raise NativeDdsError(f"DDS derivative has invalid dimensions: {width}x{height}.")
    if mip_levels <= 0:
        mip_levels = 1
    if array_size <= 0:
        raise NativeDdsError(f"DDS derivative has invalid DX10 array size: {array_size}.")

    block = _BLOCK_FORMATS.get(int(dxgi_format))
    linear = _LINEAR_FORMATS.get(int(dxgi_format))
    if block is None and linear is None:
        raise NativeDdsError(f"Unsupported native DDS DXGI format: {dxgi_format}")
    if block is not None:
        compression_family, block_bytes, is_srgb = block
        bits_per_pixel = None
    else:
        compression_family, bits_per_pixel, is_srgb = linear  # type: ignore[misc]
        block_bytes = None

    # Native material sampling currently accepts only ordinary 2D textures. The
    # parser still exposes cube/array metadata so callers can fail closed with a
    # precise reason rather than corrupting the payload layout.
    is_cube = bool(int(misc_flag) & 0x4)
    face_count = 6 if is_cube else 1
    slice_count = int(array_size) * face_count
    if resource_dimension == 4 or depth > 1:
        raise NativeDdsError(
            "Native material DDS is a 3D texture; 3D mip layout is not enabled for the FH6 viewer."
        )

    cursor = DDS_DX10_HEADER_SIZE
    first_slice_mips: list[NativeDdsMip] = []
    for slice_index in range(slice_count):
        mip_width = width
        mip_height = height
        for level in range(mip_levels):
            size = _mip_size(mip_width, mip_height, int(dxgi_format))
            end = cursor + size
            if end > len(data):
                raise NativeDdsError(
                    "DDS derivative texture payload is truncated at "
                    f"slice={slice_index}, mip={level}: need {size} bytes."
                )
            if slice_index == 0:
                first_slice_mips.append(
                    NativeDdsMip(
                        level=level,
                        width=mip_width,
                        height=mip_height,
                        offset=cursor,
                        size=size,
                    )
                )
            cursor = end
            mip_width = max(1, mip_width // 2)
            mip_height = max(1, mip_height // 2)

    # Trailing bytes are not silently interpreted. For the decoder contract the
    # DDS consists of one DX10 header plus the native texture payload exactly.
    if cursor != len(data):
        raise NativeDdsError(
            f"DDS derivative has {len(data) - cursor} unexpected trailing byte(s)."
        )

    return NativeDdsTexture(
        path=str(source),
        width=width,
        height=height,
        depth=max(depth, 1),
        mip_levels=mip_levels,
        dxgi_format=int(dxgi_format),
        resource_dimension=int(resource_dimension),
        misc_flag=int(misc_flag),
        array_size=int(array_size),
        misc_flags2=int(misc_flags2),
        is_cube=is_cube,
        is_srgb=bool(is_srgb),
        compression_family=compression_family,
        block_bytes=block_bytes,
        bits_per_pixel=bits_per_pixel,
        data_offset=DDS_DX10_HEADER_SIZE,
        data_size=len(data) - DDS_DX10_HEADER_SIZE,
        mips=tuple(first_slice_mips),
    )


def native_dds_mip_bytes(texture: NativeDdsTexture, level: int) -> bytes:
    if level < 0 or level >= len(texture.mips):
        raise NativeDdsError(f"DDS mip level is out of range: {level}")
    mip = texture.mips[level]
    try:
        with Path(texture.path).open("rb") as stream:
            stream.seek(mip.offset)
            payload = stream.read(mip.size)
    except OSError as exc:
        raise NativeDdsError(f"Could not read DDS mip {level}: {exc}") from exc
    if len(payload) != mip.size:
        raise NativeDdsError(
            f"DDS mip {level} became truncated: expected {mip.size}, got {len(payload)}."
        )
    return payload
