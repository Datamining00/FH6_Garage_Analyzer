from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog

from . import v1_4_preview_mode_shell_base as _base
from .models import LiveryRecord


class _Stage2BPreviewDialog(QDialog):
    """Wire the validated Stage-1 dialog only after it has built stable refs."""

    def exec(self) -> int:
        window = self.parent()
        record = getattr(window, "_fh6_stage2b_preview_record", None)
        if window is not None and isinstance(record, LiveryRecord):
            _wire_three_d(self, window, record)
        return super().exec()


def _wire_three_d(dialog: QDialog, window: Any, record: LiveryRecord) -> None:
    buttons = getattr(dialog, "_fh6_preview_mode_buttons", ())
    page = getattr(dialog, "_fh6_preview_3d_page", None)
    message = getattr(dialog, "_fh6_preview_3d_message", None)
    controls = getattr(dialog, "_fh6_preview_3d_controls", None)
    if len(buttons) < 3 or page is None or message is None or not isinstance(controls, dict):
        return

    three_d_button = buttons[2]
    eligibility = controls.get("eligibility")
    if eligibility is not None:
        strict_index = eligibility.findData("strict")
        if strict_index >= 0:
            # FinalVerify1_ErrorFix1 default is UV3 + Strict.
            eligibility.setCurrentIndex(strict_index)

    message.setText(
        _base._txt(
            "3D 모드는 처음 선택할 때만 준비됩니다.",
            "3D mode is prepared only when selected for the first time.",
        )
    )
    prepared = {"requested": False}
    dialog._fh6_preview_3d_prepared = prepared

    def prepare_three_d(_checked: bool = False) -> None:
        if prepared["requested"]:
            return
        prepared["requested"] = True

        callback = getattr(window, "_fh6_prepare_livery_3d_preview", None)
        if not callable(callback):
            try:
                from .preview3d.integration import _prepare_preview_3d

                callback = lambda **kwargs: _prepare_preview_3d(window, **kwargs)
            except Exception as exc:
                message.setText(
                    _base._txt(
                        "3D 백엔드를 불러올 수 없습니다.\n",
                        "Unable to load the 3D backend.\n",
                    )
                    + f"{type(exc).__name__}: {exc}"
                )
                return

        message.setText(_base._txt("3D 모델 준비 중...", "Preparing 3D model..."))

        def invoke_backend() -> None:
            try:
                callback(
                    dialog=dialog,
                    record=record,
                    page=page,
                    layout=page.layout(),
                    message=message,
                    controls=controls,
                )
            except Exception as exc:
                message.setText(
                    _base._txt(
                        "3D 모델을 표시할 수 없습니다.\n",
                        "Unable to display the 3D model.\n",
                    )
                    + f"{type(exc).__name__}: {exc}"
                )

        # Preserve the previously validated non-blocking/lifecycle boundary.
        QTimer.singleShot(0, invoke_backend)

    three_d_button.clicked.connect(prepare_three_d)


def apply_v1_4_preview_mode_shell_patch(MainWindow: Any) -> None:
    """Apply the #360 shell plus the validated lazy Stage-2b 3D connection."""
    if getattr(MainWindow, "_fh6_v14_preview_mode_shell_patched", False):
        return

    # Only this compatibility module's dialog constructor is replaced. No global
    # QSurfaceFormat or application-wide Qt behavior is changed.
    _base.QDialog = _Stage2BPreviewDialog

    original_livery_shell = _base._show_livery_preview_shell

    def show_livery_with_context(window: Any, record: LiveryRecord) -> None:
        window._fh6_stage2b_preview_record = record
        try:
            original_livery_shell(window, record)
        finally:
            try:
                delattr(window, "_fh6_stage2b_preview_record")
            except AttributeError:
                pass

    _base._show_livery_preview_shell = show_livery_with_context
    _base.apply_v1_4_preview_mode_shell_patch(MainWindow)
