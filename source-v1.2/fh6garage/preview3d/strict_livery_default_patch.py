from __future__ import annotations

from typing import Any


def select_strict_livery_default(controls: dict[str, Any]) -> bool:
    """Select Strict for the initial 3D preview without removing debug policies.

    The pinned KFPS chassis converter already classifies livery-bearing body paint
    and window glass explicitly.  Legacy UV3 promotion is useful for diagnostics,
    but it can promote unrelated UV3-bearing trim.  The production preview should
    therefore start from the converter-declared Strict contract while keeping the
    Legacy and Declared + confirmed choices available for manual diagnostics.
    """
    eligibility = controls.get("eligibility")
    if eligibility is None:
        return False
    try:
        current = str(eligibility.currentData() or "legacy").strip().casefold()
        if current != "legacy":
            return False
        index = int(eligibility.findData("strict"))
    except Exception:
        return False
    if index < 0:
        return False
    eligibility.setCurrentIndex(index)

    status = controls.get("status")
    if status is not None and hasattr(status, "setText"):
        status.setText("3D 탭을 선택하면 이 리버리를 4x / UV3 / Strict로 렌더링합니다.")
    return True


def install_strict_livery_default_patch() -> bool:
    """Patch only the initial controller construction to prefer Strict.

    Importantly, this does not rewrite load_kfps_glb and does not disable the
    Legacy combo-box option.  A user may still choose another policy after the
    initial preview has been constructed.
    """
    from . import integration

    controller = integration.Preview3DController
    if getattr(controller, "_fh6_strict_livery_default_patched", False):
        return False

    original_init = controller.__init__

    def patched_init(self, *args, **kwargs):
        controls = kwargs.get("controls")
        if isinstance(controls, dict):
            select_strict_livery_default(controls)
        original_init(self, *args, **kwargs)

    controller.__init__ = patched_init
    controller._fh6_strict_livery_default_patched = True
    return True
