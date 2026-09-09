"""Fail-closed OpenGL upload for verified native FH6 DDS derivatives."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .native_dds import NativeDdsTexture, native_dds_mip_bytes


class NativeMaterialGlError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeGlTextureSpec:
    dxgi_format: int
    family: str
    compressed: bool
    internal_format: int
    external_format: int | None = None
    external_type: int | None = None
    required_extension: str | None = None
    core_version: tuple[int, int] | None = None


# Exact OpenGL enum values from the corresponding EXT/ARB/core specifications.
# The viewer currently enables only formats suitable for the first native
# base-colour stage. Other parsed DDS formats remain available to later normal/
# roughness stages but are not silently uploaded with an approximate format.
_NATIVE_GL_SPECS: dict[int, NativeGlTextureSpec] = {
    71: NativeGlTextureSpec(71, "bc1", True, 0x83F1, required_extension="s3tc"),
    72: NativeGlTextureSpec(72, "bc1_srgb", True, 0x8C4D, required_extension="s3tc"),
    74: NativeGlTextureSpec(74, "bc2", True, 0x83F2, required_extension="s3tc"),
    75: NativeGlTextureSpec(75, "bc2_srgb", True, 0x8C4E, required_extension="s3tc"),
    77: NativeGlTextureSpec(77, "bc3", True, 0x83F3, required_extension="s3tc"),
    78: NativeGlTextureSpec(78, "bc3_srgb", True, 0x8C4F, required_extension="s3tc"),
    98: NativeGlTextureSpec(98, "bc7", True, 0x8E8C, required_extension="bptc", core_version=(4, 2)),
    99: NativeGlTextureSpec(99, "bc7_srgb", True, 0x8E8D, required_extension="bptc", core_version=(4, 2)),
    28: NativeGlTextureSpec(28, "rgba8", False, 0x8058, external_format=0x1908, external_type=0x1401),
    29: NativeGlTextureSpec(29, "rgba8_srgb", False, 0x8C43, external_format=0x1908, external_type=0x1401),
    87: NativeGlTextureSpec(87, "bgra8", False, 0x8058, external_format=0x80E1, external_type=0x1401),
}


def native_gl_texture_spec(dxgi_format: int) -> NativeGlTextureSpec:
    try:
        return _NATIVE_GL_SPECS[int(dxgi_format)]
    except (KeyError, TypeError, ValueError) as exc:
        raise NativeMaterialGlError(
            f"Native material OpenGL upload is not enabled for DXGI format {dxgi_format!r}."
        ) from exc


def _decode_gl_string(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", "ignore")
    return str(value or "")


def _gl_version(gl: Any) -> tuple[int, int]:
    try:
        raw = _decode_gl_string(gl.glGetString(gl.GL_VERSION))
    except Exception:
        return (0, 0)
    match = re.match(r"\s*(\d+)\.(\d+)", raw)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def _gl_extensions(gl: Any) -> set[str]:
    extensions: set[str] = set()
    version = _gl_version(gl)
    if version >= (3, 0) and hasattr(gl, "glGetStringi"):
        try:
            count = int(gl.glGetIntegerv(gl.GL_NUM_EXTENSIONS))
            for index in range(max(0, count)):
                text = _decode_gl_string(gl.glGetStringi(gl.GL_EXTENSIONS, index)).strip()
                if text:
                    extensions.add(text)
            return extensions
        except Exception:
            extensions.clear()
    try:
        raw = _decode_gl_string(gl.glGetString(gl.GL_EXTENSIONS))
    except Exception:
        return extensions
    extensions.update(part for part in raw.split() if part)
    return extensions


def _supports_spec(gl: Any, spec: NativeGlTextureSpec) -> bool:
    if spec.required_extension is None:
        return True
    version = _gl_version(gl)
    if spec.core_version is not None and version >= spec.core_version:
        return True
    extensions = _gl_extensions(gl)
    if spec.required_extension == "s3tc":
        return bool(
            {
                "GL_EXT_texture_compression_s3tc",
                "GL_S3_s3tc",
            }
            & extensions
        )
    if spec.required_extension == "bptc":
        return "GL_ARB_texture_compression_bptc" in extensions
    return False


def upload_native_dds_2d(gl: Any, texture: NativeDdsTexture) -> int:
    """Upload exact DDS mip payloads and return one GL texture id.

    No CPU decompression, channel swizzle, or guessed fallback format is used.
    Unsupported GPU compression capabilities fail closed before sampling.
    """
    if not texture.is_simple_2d:
        raise NativeMaterialGlError("Native material GL upload accepts ordinary 2D textures only.")
    spec = native_gl_texture_spec(texture.dxgi_format)
    if not _supports_spec(gl, spec):
        raise NativeMaterialGlError(
            f"OpenGL context does not expose the required {spec.required_extension} capability "
            f"for DXGI {texture.dxgi_format} ({spec.family})."
        )

    texture_id = int(gl.glGenTextures(1))
    if texture_id <= 0:
        raise NativeMaterialGlError("OpenGL did not allocate a native material texture object.")
    try:
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_REPEAT)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_REPEAT)
        gl.glTexParameteri(
            gl.GL_TEXTURE_2D,
            gl.GL_TEXTURE_MIN_FILTER,
            gl.GL_LINEAR_MIPMAP_LINEAR if texture.mip_levels > 1 else gl.GL_LINEAR,
        )
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)

        for mip in texture.mips:
            payload = native_dds_mip_bytes(texture, mip.level)
            if len(payload) != mip.size:
                raise NativeMaterialGlError(
                    f"Native DDS mip {mip.level} changed size during GL upload."
                )
            if spec.compressed:
                gl.glCompressedTexImage2D(
                    gl.GL_TEXTURE_2D,
                    mip.level,
                    spec.internal_format,
                    mip.width,
                    mip.height,
                    0,
                    len(payload),
                    payload,
                )
            else:
                if spec.external_format is None or spec.external_type is None:
                    raise NativeMaterialGlError("Linear DDS OpenGL mapping is incomplete.")
                gl.glTexImage2D(
                    gl.GL_TEXTURE_2D,
                    mip.level,
                    spec.internal_format,
                    mip.width,
                    mip.height,
                    0,
                    spec.external_format,
                    spec.external_type,
                    payload,
                )
            error = int(gl.glGetError()) if hasattr(gl, "glGetError") else 0
            no_error = int(getattr(gl, "GL_NO_ERROR", 0))
            if error != no_error:
                raise NativeMaterialGlError(
                    f"OpenGL rejected native DDS mip {mip.level}: error=0x{error:04X}."
                )
        return texture_id
    except Exception:
        try:
            gl.glDeleteTextures([texture_id])
        except Exception:
            pass
        raise
    finally:
        try:
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        except Exception:
            pass
