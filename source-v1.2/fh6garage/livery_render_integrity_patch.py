from __future__ import annotations

from pathlib import Path

from .livery_analysis import LIVERY_SECTION_NAMES, analyze_livery_file
from .livery_preview import LiveryPreviewError, decode_livery_preview


_APPLIED = False


def _integrity_failure_for_section(expected_counts, decoded_sections, section: str):
    """Return the first decode mismatch that can invalidate the requested section.

    C_livery sections are serialized in a fixed order. If one section is short,
    the parser's end position may also be wrong, so later sections are not
    trustworthy merely because their final count happens to match. Earlier
    sections remain usable when every section up to them is exact.
    """
    try:
        requested_index = tuple(LIVERY_SECTION_NAMES).index(str(section))
    except ValueError:
        return (str(section), 0, 0, True)

    for index, name in enumerate(LIVERY_SECTION_NAMES):
        if index > requested_index:
            break
        expected = int(expected_counts.get(name, 0))
        actual = len(decoded_sections.get(name, ()))
        if expected != actual:
            return (name, expected, actual, index < requested_index)
    return None


def verify_section_integrity(path: Path | str, section: str) -> None:
    analysis = analyze_livery_file(path)
    decoded = decode_livery_preview(path)
    failure = _integrity_failure_for_section(analysis.section_counts, decoded.sections, section)
    if failure is None:
        return

    failed_section, expected, actual, cascaded = failure
    if cascaded:
        raise LiveryPreviewError(
            f"정확 미리보기 중단: 앞선 {failed_section} 영역이 C_livery 기록 "
            f"{expected:,}개 중 {actual:,}개만 구조적으로 해석되었습니다. "
            f"이후 {section} 영역의 시작 경계도 신뢰할 수 없어 렌더링하지 않습니다."
        )
    raise LiveryPreviewError(
        f"정확 미리보기 중단: {failed_section} 영역이 C_livery 기록 "
        f"{expected:,}개 중 {actual:,}개만 구조적으로 해석되었습니다."
    )


def apply_livery_render_integrity_patch() -> None:
    """Fail closed before exact rendering when section boundaries are untrusted."""
    global _APPLIED
    if _APPLIED:
        return

    from . import livery_preview_tiled_quality as tiled_quality
    from . import v1_4_preview_final_ui_patch as final_ui

    original_scaled = tiled_quality.render_livery_section_scaled

    def render_livery_section_scaled_verified(path, section: str, scale: int = 4):
        verify_section_integrity(path, section)
        return original_scaled(path, section, scale)

    tiled_quality.render_livery_section_scaled = render_livery_section_scaled_verified
    # final_ui imported the function directly at module import time, so update
    # that bound reference as well.
    final_ui.render_livery_section_scaled = render_livery_section_scaled_verified
    _APPLIED = True
