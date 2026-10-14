from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Global shader parameter identifiers published by ForzaTechStudio's
# NameHashService at commit 4f373c5fb192551ce5249e320dd79b1399b693ca.
# Classification is hash-based only.  Filenames, vehicle names, and material
# names are deliberately not used to infer a texture role.
_NATIVE_TEXTURE_PARAMETER_NAMES: dict[int, tuple[str, str]] = {
    # Base colour / diffuse
    0x85F59336: ("DiffuseTexture", "base_color"),
    0x10350BBC: ("CH1DiffuseTextureTexture", "base_color"),
    0x294DA6FC: ("CH2DiffuseTextureTexture", "base_color"),
    0x6DD98CD9: ("DiffuseATexture", "base_color"),
    0x2B52092F: ("BaseColor_A_Texture", "base_color"),
    0x98265A4C: ("BaseColorAlpha_1", "base_color_alpha"),
    0x50D2774D: ("InteriorDiffuseTexture", "base_color"),
    0x1801459D: ("FittingsDiffuseTexture", "base_color"),

    # Geometric normals. Flake/clear-coat normals remain separate because they
    # must not replace the primary tangent-space normal map blindly.
    0x39731A8A: ("NormalMap", "normal"),
    0x8C658791: ("NormalTexture", "normal"),
    0x5BB7DA76: ("CH1NormalTexture", "normal"),
    0x27D6FFAD: ("CH2NormalTexture", "normal"),
    0x5F37B059: ("NormalMapWithIntensityTexture", "normal"),
    0x3C929217: ("CH1_CLCNormalMap0Texture", "clearcoat_normal"),
    0xB59BE3AB: ("FlakeNormalTexture", "flake_normal"),

    # Surface response / masks
    0x7E4A41E1: ("GlossTexture", "gloss"),
    0xECE98535: ("GlassRoughnessTexture", "roughness"),
    0x7FDA2F1B: ("LocalAOTexture", "ambient_occlusion"),
    0x0FEA383B: ("AOTexture", "ambient_occlusion"),
    0x3380008B: ("CH1MaskTexture", "material_mask"),
    0x022DF609: ("CH1GlossDiffMaskTexture", "gloss_diffuse_mask"),
    0x3A72873C: ("CH1NormalMaskTexture", "normal_mask"),
    0x220CAD2C: ("RTintTexture", "reflection_tint"),
    0x4049C803: ("CH2RTintTexture", "reflection_tint"),

    # Alpha / transparency
    0x57D9D49E: ("AlphaTexture", "alpha"),
    0x66E53F62: ("CH1AlphaTextureTexture", "alpha"),
    0x2FDCDBF0: ("AlphaTexture_1", "alpha"),

    # Lighting / emissive
    0x4E0D5E89: ("CH1EmissiveMap", "emissive"),
    0x020B22EB: ("EmissiveMap", "emissive"),
    0x212B4B48: ("EmissiveTexture", "emissive"),
    0x3CB4DFCB: ("InteriorEmissiveTexture", "emissive"),
    0x35C82561: ("LightMapTexture", "lightmap"),
}


@dataclass(frozen=True)
class NativeTextureSemantic:
    parameter_hash: str
    parameter_name: str | None
    semantic: str
    resolution_mode: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_parameter_hash(value: str | int | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 0xFFFFFFFF else None
    text = str(value).strip()
    if not text:
        return None
    if text.casefold().startswith("0x"):
        text = text[2:]
    if len(text) > 8:
        return None
    try:
        parsed = int(text, 16)
    except ValueError:
        return None
    return parsed if 0 <= parsed <= 0xFFFFFFFF else None


def classify_native_texture_parameter(value: str | int | None) -> NativeTextureSemantic:
    parsed = normalize_parameter_hash(value)
    if parsed is None:
        return NativeTextureSemantic(
            parameter_hash="",
            parameter_name=None,
            semantic="unknown",
            resolution_mode="invalid_parameter_hash",
        )
    hash_text = f"{parsed:08X}"
    known = _NATIVE_TEXTURE_PARAMETER_NAMES.get(parsed)
    if known is None:
        return NativeTextureSemantic(
            parameter_hash=hash_text,
            parameter_name=None,
            semantic="unknown",
            resolution_mode="unmapped_parameter_hash",
        )
    parameter_name, semantic = known
    return NativeTextureSemantic(
        parameter_hash=hash_text,
        parameter_name=parameter_name,
        semantic=semantic,
        resolution_mode="forzatechstudio_namehash_exact",
    )


def known_native_texture_parameter_count() -> int:
    return len(_NATIVE_TEXTURE_PARAMETER_NAMES)


def known_native_texture_parameters() -> dict[int, tuple[str, str]]:
    return dict(_NATIVE_TEXTURE_PARAMETER_NAMES)
