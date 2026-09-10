from __future__ import annotations

from typing import Any


HYBRID_LABEL = "Hybrid — Strict + verified exterior recovery"


def ensure_hybrid_livery_option(controls: dict[str, Any]) -> bool:
    """Expose the guarded Hybrid test mode while keeping Legacy as the default."""
    eligibility = controls.get("eligibility")
    if eligibility is None:
        return False
    try:
        if int(eligibility.findData("hybrid")) >= 0:
            return False
        eligibility.addItem(HYBRID_LABEL, "hybrid")
    except Exception:
        return False
    return True


def select_legacy_livery_default(controls: dict[str, Any]) -> bool:
    """Select Legacy initially while retaining Strict/confirmed/Hybrid diagnostics."""
    eligibility = controls.get("eligibility")
    if eligibility is None:
        return False
    try:
        current = str(eligibility.currentData() or "legacy").strip().casefold()
        index = int(eligibility.findData("legacy"))
    except Exception:
        return False
    if index < 0:
        return False
    changed = current != "legacy"
    if changed:
        eligibility.setCurrentIndex(index)

    status = controls.get("status")
    if status is not None and hasattr(status, "setText"):
        status.setText(
            "3D 탭을 선택하면 이 리버리를 4x / UV3 / Legacy로 렌더링합니다. "
            "Hybrid/Strict는 옵션에서 비교할 수 있습니다."
        )
    return changed


# Compatibility alias retained for older imports/tests/plugins.  Its behavior now
# follows the product decision to ship Legacy as the default.
def select_strict_livery_default(controls: dict[str, Any]) -> bool:
    return select_legacy_livery_default(controls)


def install_strict_livery_default_patch() -> bool:
    """Add Hybrid to the selector and force initial production preview to Legacy."""
    from . import integration

    controller = integration.Preview3DController
    if getattr(controller, "_fh6_strict_livery_default_patched", False):
        return False

    original_init = controller.__init__

    def patched_init(self, *args, **kwargs):
        controls = kwargs.get("controls")
        if isinstance(controls, dict):
            ensure_hybrid_livery_option(controls)
            select_legacy_livery_default(controls)
        original_init(self, *args, **kwargs)

    controller.__init__ = patched_init
    controller._fh6_strict_livery_default_patched = True
    return True
