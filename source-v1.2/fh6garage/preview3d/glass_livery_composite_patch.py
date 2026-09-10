"""Keep glass transmission from attenuating livery coverage in the FH6 preview.

Reference contract:
* Khronos glTF treats material transmission as light passing through the surface,
  distinct from alpha coverage.
* KFPS keeps livery-bearing paint and glass surfaces plus their section masks as
  separate authoring/render contracts.

The established material shader first resolves native/base albedo and then the
livery decal.  For transmissive glass, shading that already-composited albedo
with transmission makes the decal itself inherit glass transmission and appear
washed out.  This final shader-stage patch preserves the glass substrate and,
only when both transmission and livery coverage are present, shades the livery
surface without substrate transmission before compositing by the livery's own
alpha. Opaque paint follows the existing path unchanged.

No game/save data or geometry is modified.
"""

from __future__ import annotations

_PATCH_MARKER = "_fh6_glass_livery_composite_patched"
_SUBSTRATE_MARKER = "                albedo = mix(albedo, decalLinear, decal.a);\n"
_SHADED_MARKER = """                vec3 shaded = fh6ShadeMaterial(
                    albedo,
                    N,
                    V,
                    effectiveMaterialParams,
                    clamp(vMaterialAux.x, 0.0, 1.0),
                    vMaterialF0,
                    vMaterialCoatF0,
                    effectiveEmission);
"""


def upgrade_glass_livery_fragment_shader(fragment: str) -> str:
    """Separate transmissive substrate shading from livery alpha coverage."""
    if "fh6GlassLiverySeparated" in fragment:
        return fragment
    if _SUBSTRATE_MARKER not in fragment or _SHADED_MARKER not in fragment:
        return fragment

    upgraded = fragment.replace(
        _SUBSTRATE_MARKER,
        "                vec3 glassSubstrateAlbedo = albedo;\n"
        + _SUBSTRATE_MARKER,
        1,
    )

    separated = _SHADED_MARKER + """                // fh6GlassLiverySeparated: transmission belongs to the glass
                // substrate, while decal.a remains the livery's own coverage.
                float glassTransmission = clamp(vMaterialAux.x, 0.0, 1.0);
                if (glassTransmission > 0.0 && decal.a > 0.0) {
                    vec3 glassSubstrateShaded = fh6ShadeMaterial(
                        glassSubstrateAlbedo,
                        N,
                        V,
                        effectiveMaterialParams,
                        glassTransmission,
                        vMaterialF0,
                        vMaterialCoatF0,
                        effectiveEmission);
                    vec3 liverySurfaceShaded = fh6ShadeMaterial(
                        decalLinear,
                        N,
                        V,
                        effectiveMaterialParams,
                        0.0,
                        vMaterialF0,
                        vMaterialCoatF0,
                        effectiveEmission);
                    shaded = mix(glassSubstrateShaded, liverySurfaceShaded, decal.a);
                }
"""
    return upgraded.replace(_SHADED_MARKER, separated, 1)


def install_glass_livery_composite_patch() -> bool:
    """Install after native base/normal/emissive shader upgrades."""
    from . import glb_viewer, native_material_texture_patch as texture_patch

    widget_class = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget_class, _PATCH_MARKER, False)):
        return False

    original_fragment_upgrade = texture_patch.upgrade_native_texture_fragment_shader

    def _fragment_upgrade_with_glass_livery(fragment: str) -> str:
        return upgrade_glass_livery_fragment_shader(original_fragment_upgrade(fragment))

    texture_patch.upgrade_native_texture_fragment_shader = _fragment_upgrade_with_glass_livery
    setattr(widget_class, _PATCH_MARKER, True)
    return True
