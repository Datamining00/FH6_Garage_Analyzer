from __future__ import annotations

from .pipeline_diagnostics import trace_worker, record

from dataclasses import replace
import re
from typing import Any

import numpy as np
from PySide6.QtWidgets import QCheckBox


_EXACT_WHEEL_TIRE_PART_TYPES = {"wheelstyle", "tire", "tyre"}
_EXACT_OTHER_MECHANICAL_PART_TYPES = {"brakes"}
_WHEEL_TIRE_WORDS = {"wheel", "wheels", "wheelstyle", "rim", "rims", "tire", "tires", "tyre", "tyres"}
_OTHER_MECHANICAL_WORDS = {
    "brake", "brakes", "caliper", "calipers", "rotor", "rotors", "disc", "discs",
    "suspension", "controlarm", "controlarms", "knuckle", "knuckles", "upright", "uprights",
    "hub", "hubs", "axle", "axles", "driveshaft", "driveshafts", "shaft", "shafts", "strut", "struts",
    "tierod", "tierods", "wishbone", "wishbones", "carrier", "carriers", "subframe", "subframes",
}


def _words(value: Any) -> set[str]:
    """Tokenize identifiers without substring matches such as rim -> PrimaryLights."""
    text = str(value or "").replace("\\", "/")
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return {
        token.casefold()
        for token in re.split(r"[^A-Za-z0-9]+", text)
        if token
    }


def _fallback_words(item: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for key in ("mesh_name", "material_name", "source_entry", "source_tire_entry", "instance_identity"):
        result.update(_words(item.get(key)))
    return result


def classify_part_group(item: dict[str, Any]) -> str:
    """Classify display-only mechanical groups using structured KFPS evidence first."""
    part_type = str(item.get("part_type") or "").strip().casefold()

    # Tires merged by the production native-tire path are explicitly authored as
    # fh6_native_tire_trial nodes. Treat that provenance as authoritative even if
    # their derivative mesh has no KFPS PartType.
    if bool(item.get("fh6_native_tire_trial")):
        return "wheel_tire"
    if part_type in _EXACT_WHEEL_TIRE_PART_TYPES:
        return "wheel_tire"
    if part_type in _EXACT_OTHER_MECHANICAL_PART_TYPES:
        return "other_mechanical"

    words = _fallback_words(item)
    if words & _WHEEL_TIRE_WORDS:
        return "wheel_tire"
    if words & _OTHER_MECHANICAL_WORDS:
        return "other_mechanical"
    return "other"


def filter_scene_part_visibility(scene: Any, *, show_wheel_tire: bool, show_other: bool) -> Any:
    """Filter primitive index ranges from an unfiltered scene; source data stay untouched."""
    indices = np.asarray(scene.indices, dtype=np.uint32).reshape(-1)
    diagnostics: list[dict[str, Any]] = []
    kept: list[np.ndarray] = []
    cursor = 0

    for raw in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
        item = dict(raw)
        count = max(0, int(item.get("triangle_count") or 0)) * 3
        end = min(cursor + count, len(indices))
        block = indices[cursor:end]
        cursor = end
        group = classify_part_group(item)
        visible = not (
            (group == "wheel_tire" and not show_wheel_tire)
            or (group == "other_mechanical" and not show_other)
        )
        item["preview_part_group"] = group
        item["preview_part_visible"] = visible
        if visible:
            kept.append(block)
        diagnostics.append(item)

    if cursor < len(indices):
        kept.append(indices[cursor:])
    filtered = np.concatenate(kept).astype(np.uint32, copy=False) if kept else np.empty((0,), dtype=np.uint32)
    return replace(
        scene,
        indices=np.ascontiguousarray(filtered, dtype=np.uint32),
        triangle_count=int(len(filtered) // 3),
        primitive_diagnostics=tuple(diagnostics),
    )


def _add_visibility_controls(controller: Any) -> None:
    controls = controller.controls
    if "show_wheel_tire" in controls:
        return
    parent = controls["apply"].parentWidget()
    layout = parent.layout() if parent is not None else None
    if layout is None:
        return

    specs = (
        ("show_wheel_tire", "휠/타이어", "휠·림·타이어 표시", True),
        ("show_other", "기타", "브레이크·디스크·허브·차축·서스펜션 등 기타 기계부품 표시", False),
    )
    insert_at = max(0, layout.count() - 3)
    for key, label, tip, checked in specs:
        box = QCheckBox(label, parent)
        box.setChecked(bool(checked))
        box.setToolTip(tip)
        layout.insertWidget(insert_at, box)
        insert_at += 1
        controls[key] = box


def install_part_visibility_patch() -> bool:
    from . import integration

    controller = integration.Preview3DController
    if getattr(controller, "_fh6_part_visibility_patched", False):
        return False

    original_init = controller.__init__
    original_install_scene = controller._install_scene
    original_enable = controller._set_controls_enabled

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._fh6_unfiltered_scene = None
        _add_visibility_controls(self)

    def patched_enable(self, enabled):
        original_enable(self, enabled)
        for key in ("show_wheel_tire", "show_other"):
            widget = self.controls.get(key)
            if widget is not None:
                widget.setEnabled(bool(enabled))

    @trace_worker
    def patched_install_scene(self, scene):
        record("visibility_state",
               wheel_tire=self.controls["show_wheel_tire"].isChecked() if self.controls.get("show_wheel_tire") else True,
               other=self.controls["show_other"].isChecked() if self.controls.get("show_other") else False)
        if scene is not None:
            # SceneReloadWorker reparses the full GLB. Preserve that full source and
            # always derive visibility from it. Never filter a previously filtered
            # scene, so OFF -> ON restores geometry in the same session.
            already_filtered = any(
                isinstance(row, dict) and "preview_part_visible" in row
                for row in tuple(getattr(scene, "primitive_diagnostics", ()) or ())
            )
            if not already_filtered:
                self._fh6_unfiltered_scene = scene
            base_scene = self._fh6_unfiltered_scene or scene
            scene = filter_scene_part_visibility(
                base_scene,
                show_wheel_tire=bool(self.controls.get("show_wheel_tire").isChecked()) if self.controls.get("show_wheel_tire") else True,
                show_other=bool(self.controls.get("show_other").isChecked()) if self.controls.get("show_other") else False,
            )
        return original_install_scene(self, scene)

    controller.__init__ = patched_init
    controller._set_controls_enabled = patched_enable
    controller._install_scene = patched_install_scene
    controller._fh6_part_visibility_patched = True
    return True
