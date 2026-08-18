from __future__ import annotations

import io
from dataclasses import replace
from typing import Any

from PySide6.QtWidgets import QLabel

from .i18n import get_language
from .livery_analysis import LIVERY_SECTION_NAMES, LiveryAnalysisError, analyze_livery_file
from .livery_preview import LiveryPreviewError, decode_livery_preview


_APPLIED = False


def _ko() -> bool:
    return str(get_language() or "").lower().startswith("ko")


def _summary_text(expected_total: int, decoded_total: int, mismatches: list[tuple[str, int, int]]) -> str:
    if not mismatches:
        if _ko():
            return f"placement 검증: 정상 · 기록 {expected_total:,} / 해석 {decoded_total:,} · 11개 영역 일치"
        return f"Placement verification: OK · recorded {expected_total:,} / decoded {decoded_total:,} · all 11 sections match"

    preview = ", ".join(
        f"{section} {expected:,}->{decoded:,}"
        for section, expected, decoded in mismatches[:4]
    )
    if len(mismatches) > 4:
        preview += f" +{len(mismatches) - 4}"
    if _ko():
        return (
            f"placement 검증 경고: 기록 {expected_total:,} / 해석 {decoded_total:,} · "
            f"불일치 {len(mismatches)}개 영역 ({preview})"
        )
    return (
        f"Placement verification warning: recorded {expected_total:,} / decoded {decoded_total:,} · "
        f"{len(mismatches)} section mismatch(es) ({preview})"
    )


def compare_counts(expected_counts: dict[str, int], decoded_sections: dict[str, tuple[dict, ...]]) -> tuple[int, int, list[tuple[str, int, int]]]:
    expected_total = 0
    decoded_total = 0
    mismatches: list[tuple[str, int, int]] = []
    for section in LIVERY_SECTION_NAMES:
        expected = int(expected_counts.get(section, 0))
        decoded = len(decoded_sections.get(section, ()))
        expected_total += expected
        decoded_total += decoded
        if expected != decoded:
            mismatches.append((section, expected, decoded))
    return expected_total, decoded_total, mismatches


def _overlay_validation_warning(png_bytes: bytes, message: str) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont

        with Image.open(io.BytesIO(png_bytes)) as source:
            image = source.convert("RGB")
        width, height = image.size
        banner_h = max(44, min(82, height // 11))
        overlay = Image.new("RGB", (width, banner_h), (70, 47, 18))
        image.paste(overlay, (0, height - banner_h))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        text = message
        if len(text) > 150:
            text = text[:147] + "..."
        draw.text((14, height - banner_h + 12), text, fill=(255, 239, 208), font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except Exception:
        return png_bytes


def apply_v1_4_validation_patch() -> None:
    """Add automatic recorded-vs-decoded placement verification to v1.4."""
    global _APPLIED
    if _APPLIED:
        return

    from . import v1_4_patch

    original_build_panel = v1_4_patch._build_analysis_panel
    original_render_section = v1_4_patch.render_livery_section

    def validated_build_panel(record: Any):
        panel = original_build_panel(record)
        source = getattr(record, "livery_path", None)
        layout = panel.layout()
        if source is None or layout is None:
            return panel
        try:
            analysis = analyze_livery_file(source)
            decoded = decode_livery_preview(source)
            expected_total, decoded_total, mismatches = compare_counts(
                analysis.section_counts,
                decoded.sections,
            )
            label = QLabel(_summary_text(expected_total, decoded_total, mismatches))
            label.setWordWrap(True)
            if mismatches:
                label.setStyleSheet("color:#8a5b16;font-size:9pt;")
            else:
                label.setStyleSheet("color:#2f7d4a;font-size:9pt;")
            layout.addWidget(label)
        except (LiveryAnalysisError, LiveryPreviewError) as exc:
            label = QLabel(
                ("placement 상세 검증 대기: " if _ko() else "Detailed placement verification unavailable: ")
                + str(exc)
            )
            label.setWordWrap(True)
            label.setStyleSheet("color:#737787;font-size:8.8pt;")
            layout.addWidget(label)
        return panel

    def validated_render_section(path, section: str):
        result = original_render_section(path, section)
        try:
            analysis = analyze_livery_file(path)
            expected = int(analysis.section_counts.get(section, 0))
        except LiveryAnalysisError:
            return result
        actual = int(result.placement_count)
        if expected == actual:
            return result

        if _ko():
            warning = f"검증 경고: C_livery 기록 {expected:,} / placement 해석 {actual:,}"
        else:
            warning = f"Verification warning: C_livery recorded {expected:,} / decoded {actual:,}"
        return replace(
            result,
            png_bytes=_overlay_validation_warning(result.png_bytes, warning),
            warnings=tuple(dict.fromkeys((*result.warnings, warning))),
        )

    v1_4_patch._build_analysis_panel = validated_build_panel
    v1_4_patch.render_livery_section = validated_render_section
    _APPLIED = True
