from fh6garage.preview3d.glass_livery_composite_patch import (
    upgrade_glass_livery_fragment_shader,
)


def _fragment() -> str:
    return """
                vec3 albedo = vec3(0.2);
                albedo = mix(albedo, decalLinear, decal.a);
                vec3 shaded = fh6ShadeMaterial(
                    albedo,
                    N,
                    V,
                    effectiveMaterialParams,
                    clamp(vMaterialAux.x, 0.0, 1.0),
                    vMaterialF0,
                    vMaterialCoatF0,
                    effectiveEmission);
                fragColor = vec4(shaded, 1.0);
"""


def test_glass_livery_separates_transmission_from_decal_coverage() -> None:
    upgraded = upgrade_glass_livery_fragment_shader(_fragment())

    assert "vec3 glassSubstrateAlbedo = albedo;" in upgraded
    assert "float glassTransmission = clamp(vMaterialAux.x, 0.0, 1.0);" in upgraded
    assert "if (glassTransmission > 0.0 && decal.a > 0.0)" in upgraded
    assert "vec3 glassSubstrateShaded = fh6ShadeMaterial(" in upgraded
    assert "vec3 liverySurfaceShaded = fh6ShadeMaterial(" in upgraded
    assert "                        0.0," in upgraded
    assert "shaded = mix(glassSubstrateShaded, liverySurfaceShaded, decal.a);" in upgraded


def test_glass_livery_upgrade_is_idempotent() -> None:
    first = upgrade_glass_livery_fragment_shader(_fragment())
    second = upgrade_glass_livery_fragment_shader(first)
    assert second == first


def test_glass_livery_upgrade_fails_closed_without_expected_shader_contract() -> None:
    fragment = "void main() { fragColor = vec4(1.0); }"
    assert upgrade_glass_livery_fragment_shader(fragment) == fragment
