from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
from PySide6.QtWidgets import QCheckBox


_WHEEL_TIRE_TOKENS = ("wheelstyle", "wheel", "rim", "tire", "tyre")
_BRAKE_TOKENS = ("brakes", "brake", "caliper", "rotor", "disc")
_UNDERBODY_TOKENS = (
    "suspension", "controlarm", "control_arm", "knuckle", "upright",
    "hub", "axle", "driveshaft", "drive_shaft", "shaft", "strut",
    "tierod", "tie_rod", "wishbone", "carrier", "subframe",
)


def _identity(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("part_type", "mesh_name", "material_name", "source_entry")
    ).casefold().replace("\\", "/")


def classify_part_group(item: dict[str, Any]) -> str:
    text = _identity(item)
    if any(token in text for token in _WHEEL_TIRE_TOKENS):
        return "wheel_tire"
    if any(token in text for token in _BRAKE_TOKENS):
        return "brake"
    if any(token in text for token in _UNDERBODY_TOKENS):
        return "underbody"
    return "other"


def filter_scene_part_visibility(scene: Any, *, show_wheel_tire: bool, show_brake: bool, show_underbody: bool) -> Any:
    """Filter primitive index ranges only; source GLB and game data remain untouched."""
    indices = np.asarray(scene.indices, dtype=np.uint32).reshape(-1)
    diagnostics: list[dict[str, Any]] = []
    kept: list[np.ndarray] = []
    cursor = 0
    hidden_counts = {"wheel_tire": 0, "brake": 0, "underbody": 0}

    for raw in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
        item = dict(raw)
        count = max(0, int(item.get("triangle_count") or 0)) * 3
        end = min(cursor + count, len(indices))
        block = indices[cursor:end]
        cursor = end
        group = classify_part_group(item)
        visible = not (
            (group == "wheel_tire" and not show_wheel_tire)
            or (group == "brake" and not show_brake)
            or (group == "underbody" and not show_underbody)
        )
        item["preview_part_group"] = group
        item["preview_part_visible"] = visible
        if visible:
            kept.append(block)
        elif group in hidden_counts:
            hidden_counts[group] += 1
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
        ("show_wheel_tire", "휠/타이어", "휠·림·타이어 표시"),
        ("show_brake", "브레이크", "캘리퍼·브레이크 디스크 표시"),
        ("show_underbody", "하부기계", "허브·차축·서스펜션 등 하부 기계부품 표시"),
    )
    insert_at = max(0, layout.count() - 3)
    for key, label, tip in specs:
        box = QCheckBox(label, parent)
        box.setChecked(True)
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
        _add_visibility_controls(self)

    def patched_enable(self, enabled):
        original_enable(self, enabled)
        for key in ("show_wheel_tire", "show_brake", "show_underbody"):
            widget = self.controls.get(key)
            if widget is not None:
                widget.setEnabled(bool(enabled))

    def patched_install_scene(self, scene):
        if scene is not None:
            scene = filter_scene_part_visibility(
                scene,
                show_wheel_tire=bool(self.controls.get("show_wheel_tire").isChecked()) if self.controls.get("show_wheel_tire") else True,
                show_brake=bool(self.controls.get("show_brake").isChecked()) if self.controls.get("show_brake") else True,
                show_underbody=bool(self.controls.get("show_underbody").isChecked()) if self.controls.get("show_underbody") else True,
            )
        return original_install_scene(self, scene)

    controller.__init__ = patched_init
    controller._set_controls_enabled = patched_enable
    controller._install_scene = patched_install_scene
    controller._fh6_part_visibility_patched = True
    return True
