from __future__ import annotations

import unittest

from fh6garage.preview3d.tire_morph_boundary_roles import (
    TireMorphBoundaryRoleError,
    analyze_selector_state_boundaries,
)


def _state(minimum, maximum):
    return {"aabb": {"minimum": minimum, "maximum": maximum}}


class TireMorphBoundaryRoleTests(unittest.TestCase):
    def test_classifies_actual_slick_like_selector_responses(self) -> None:
        states = {
            "baseline": _state((-0.0032, -0.2248, -0.2247), (1.0032, 0.2248, 0.2247)),
            "selector0": _state((0.0, -0.4994, -0.4996), (1.0032, 0.4994, 0.4996)),
            "selector1": _state((-0.0032, -0.3296, -0.3291), (1.0032, 0.3296, 0.3291)),
            "selector2": _state((-0.1415, -0.1522, -0.1522), (1.1682, 0.1522, 0.1522)),
            "selector3": _state((0.0, -0.2248, -0.2247), (1.2970, 0.2248, 0.2247)),
            "selector4": _state((-0.2955, -0.2248, -0.2247), (1.0, 0.2248, 0.2247)),
        }
        roles = analyze_selector_state_boundaries(states)
        self.assertEqual(
            [item.geometric_role for item in roles],
            [
                "radial_expansion_dominant",
                "radial_expansion_dominant",
                "mixed_x_expansion_radial_contraction",
                "positive_x_boundary_expansion",
                "negative_x_boundary_expansion",
            ],
        )
        self.assertTrue(all(item.production_semantics_assigned is False for item in roles))
        self.assertEqual(roles[3].confidence, "high")
        self.assertEqual(roles[4].confidence, "high")

    def test_positive_and_negative_boundary_controls_are_not_confused_with_uniform_width(self) -> None:
        states = {
            "baseline": _state((-0.5, -0.2, -0.2), (0.5, 0.2, 0.2)),
            "selector0": _state((-0.5, -0.4, -0.4), (0.5, 0.4, 0.4)),
            "selector1": _state((-0.5, -0.3, -0.3), (0.5, 0.3, 0.3)),
            "selector2": _state((-0.7, -0.1, -0.1), (0.7, 0.1, 0.1)),
            "selector3": _state((-0.5, -0.2, -0.2), (0.8, 0.2, 0.2)),
            "selector4": _state((-0.8, -0.2, -0.2), (0.5, 0.2, 0.2)),
        }
        roles = analyze_selector_state_boundaries(states)
        self.assertEqual(roles[3].geometric_role, "positive_x_boundary_expansion")
        self.assertEqual(roles[4].geometric_role, "negative_x_boundary_expansion")
        self.assertGreater(roles[3].x.maximum_delta, 0.0)
        self.assertLess(roles[4].x.minimum_delta, 0.0)

    def test_missing_selector_fails_closed(self) -> None:
        with self.assertRaisesRegex(TireMorphBoundaryRoleError, "selector4 state is missing"):
            analyze_selector_state_boundaries({
                "baseline": _state((0, 0, 0), (1, 1, 1)),
                "selector0": _state((0, 0, 0), (1, 1, 1)),
                "selector1": _state((0, 0, 0), (1, 1, 1)),
                "selector2": _state((0, 0, 0), (1, 1, 1)),
                "selector3": _state((0, 0, 0), (1, 1, 1)),
            })


if __name__ == "__main__":
    unittest.main()
