"""Game-like preview material shading without changing FH6 geometry/livery mapping."""

from __future__ import annotations

_PATCH_MARKER = "_fh6_game_like_material_shading_patched"

_FLAT_LIGHTING = """                vec3 N = normalize(vNormal);
                vec3 L = normalize(vec3(0.45, 0.85, 0.55));
                float d = max(dot(N, L), 0.0);
                vec3 V = normalize(uEye - vWorld);
                float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
                vec3 base = vColor * (0.34 + 0.66 * d) + vec3(0.08, 0.11, 0.14) * rim;
"""

_PBR_MAIN_START = """                vec3 N = normalize(vNormal);
                vec3 V = normalize(uEye - vWorld);
"""

_FLAT_OUTPUT = """                if (uDebugSections && bestSlot >= 0) {
                    fragColor = vec4(mix(base, debugColor(bestSlot), max(bestCoverage, 0.55)), 1.0);
                } else {
                    fragColor = vec4(mix(base, decal.rgb, decal.a), 1.0);
                }
"""

_PBR_OUTPUT = """                vec3 decalLinear = pow(max(decal.rgb, vec3(0.0)), vec3(2.2));
                vec3 albedo = pow(clamp(vColor, 0.0, 1.0), vec3(2.2));
                albedo = mix(albedo, decalLinear, decal.a);
                vec3 shaded = fh6ShadeMaterial(albedo, N, V, vColor);

                if (uDebugSections && bestSlot >= 0) {
                    fragColor = vec4(mix(shaded, debugColor(bestSlot), max(bestCoverage, 0.55)), 1.0);
                } else {
                    fragColor = vec4(shaded, 1.0);
                }
"""

_PBR_HELPERS = r"""
            const float FH6_PI = 3.14159265359;

            float fh6DistributionGGX(vec3 N, vec3 H, float roughness) {
                float a = max(roughness * roughness, 0.0025);
                float a2 = a * a;
                float ndh = max(dot(N, H), 0.0);
                float ndh2 = ndh * ndh;
                float denom = ndh2 * (a2 - 1.0) + 1.0;
                return a2 / max(FH6_PI * denom * denom, 0.000001);
            }

            float fh6GeometrySchlickGGX(float ndv, float roughness) {
                float r = roughness + 1.0;
                float k = (r * r) * 0.125;
                return ndv / max(ndv * (1.0 - k) + k, 0.000001);
            }

            float fh6GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
                return fh6GeometrySchlickGGX(max(dot(N, V), 0.0), roughness)
                     * fh6GeometrySchlickGGX(max(dot(N, L), 0.0), roughness);
            }

            vec3 fh6FresnelSchlick(float cosTheta, vec3 F0) {
                return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
            }

            vec4 fh6MaterialParams(vec3 roleColor) {
                if (distance(roleColor, vec3(0.72, 0.75, 0.78)) < 0.06)
                    return vec4(0.08, 0.25, 0.95, 0.08);
                if (distance(roleColor, vec3(0.25, 0.43, 0.55)) < 0.06)
                    return vec4(0.00, 0.08, 0.35, 0.05);
                if (distance(roleColor, vec3(0.10, 0.11, 0.12)) < 0.06)
                    return vec4(0.00, 0.70, 0.02, 0.35);
                return vec4(0.28, 0.40, 0.18, 0.18);
            }

            float fh6Transmission(vec3 roleColor) {
                return distance(roleColor, vec3(0.25, 0.43, 0.55)) < 0.06 ? 0.72 : 0.0;
            }

            vec3 fh6Environment(vec3 direction) {
                float sky = clamp(direction.y * 0.5 + 0.5, 0.0, 1.0);
                vec3 ground = vec3(0.055, 0.060, 0.070);
                vec3 horizon = vec3(0.24, 0.27, 0.31);
                vec3 zenith = vec3(0.52, 0.61, 0.72);
                vec3 upper = mix(horizon, zenith, smoothstep(0.15, 1.0, sky));
                return mix(ground, upper, smoothstep(0.0, 0.55, sky));
            }

            vec3 fh6ShadeMaterial(vec3 albedo, vec3 N, vec3 V, vec3 roleColor) {
                vec4 p = fh6MaterialParams(roleColor);
                float metallic = p.x;
                float roughness = p.y;
                float clearcoat = p.z;
                float coatRoughness = p.w;

                vec3 L = normalize(vec3(0.42, 0.82, 0.38));
                vec3 H = normalize(V + L);
                float ndl = max(dot(N, L), 0.0);
                float ndv = max(dot(N, V), 0.0);
                float ndh = max(dot(N, H), 0.0);
                float vdh = max(dot(V, H), 0.0);

                vec3 F0 = mix(vec3(0.04), albedo, metallic);
                vec3 F = fh6FresnelSchlick(vdh, F0);
                float D = fh6DistributionGGX(N, H, roughness);
                float G = fh6GeometrySmith(N, V, L, roughness);
                vec3 specular = (D * G * F) / max(4.0 * ndv * ndl, 0.001);
                vec3 kd = (vec3(1.0) - F) * (1.0 - metallic);
                vec3 direct = (kd * albedo / FH6_PI + specular)
                            * vec3(3.8, 3.6, 3.35) * ndl;

                vec3 R = reflect(-V, N);
                vec3 environment = fh6Environment(R);
                vec3 envF = fh6FresnelSchlick(ndv, F0);
                float hemi = clamp(N.y * 0.5 + 0.5, 0.0, 1.0);
                vec3 ambient = albedo * mix(0.045, 0.14, hemi) * (1.0 - metallic)
                             + environment * envF * mix(0.55, 0.16, roughness);

                float coatPower = mix(256.0, 28.0, clamp(coatRoughness, 0.0, 1.0));
                float coatHighlight = pow(ndh, coatPower) * clearcoat;
                vec3 coatF = fh6FresnelSchlick(ndv, vec3(0.04));
                vec3 color = direct + ambient + coatF * coatHighlight * 2.1;

                float transmission = fh6Transmission(roleColor);
                if (transmission > 0.0) {
                    vec3 glassEnvironment = fh6Environment(R) * (vec3(0.72) + 0.28 * envF);
                    color = mix(color, glassEnvironment + albedo * 0.12, transmission);
                }

                color = max(color, vec3(0.0));
                color = color / (color + vec3(1.0));
                return pow(color, vec3(1.0 / 2.2));
            }
"""


def upgrade_fragment_shader(fragment: str) -> str:
    """Upgrade the current FHA flat shader while preserving livery UV/mask logic."""
    if "fh6ShadeMaterial(" in fragment:
        return fragment
    if _FLAT_LIGHTING not in fragment or _FLAT_OUTPUT not in fragment:
        return fragment
    upgraded = fragment.replace(
        "            void main() {\n",
        _PBR_HELPERS + "\n            void main() {\n",
        1,
    )
    upgraded = upgraded.replace(_FLAT_LIGHTING, _PBR_MAIN_START, 1)
    return upgraded.replace(_FLAT_OUTPUT, _PBR_OUTPUT, 1)


def install_game_like_material_patch() -> bool:
    """Install the shading bridge exactly once on the production OpenGL viewer."""
    from . import glb_viewer

    widget = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget, _PATCH_MARKER, False)):
        return False

    original = widget._make_program.__func__

    def _make_program_with_materials(cls, vertex: str, fragment: str) -> int:
        return original(cls, vertex, upgrade_fragment_shader(fragment))

    widget._make_program = classmethod(_make_program_with_materials)
    setattr(widget, _PATCH_MARKER, True)
    return True
