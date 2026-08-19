from __future__ import annotations

from pathlib import Path

from .livery_analysis import LIVERY_SECTION_NAMES, analyze_livery_file
from .livery_preview import LiveryPreviewError, _load_backend, decode_livery_preview


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


def _raster_provenance_failure(decoder, body: bytes, layers):
    """Return a decoder inconsistency when a claimed raster layer is not raster in source bytes."""
    end = len(body)
    for layer_index, layer in enumerate(layers, 1):
        if not bool(layer.get("is_raster_logo")):
            continue
        try:
            raster_id = int(layer.get("raster_id"))
        except (TypeError, ValueError):
            return (layer_index, None, "decoded raster ID is invalid")
        try:
            offset = int(layer.get("source_offset"))
        except (TypeError, ValueError):
            return (layer_index, raster_id, "source offset is unavailable")
        if offset < 0 or offset + 32 > end:
            return (layer_index, raster_id, f"source offset 0x{offset:X} is outside the livery body")
        try:
            raw_is_raster = bool(decoder.is_livery_logo_at(body, offset, end))
        except Exception:
            raw_is_raster = False
        if not raw_is_raster:
            return (layer_index, raster_id, f"source bytes at 0x{offset:X} are not a raster placement")
        raw_id = int.from_bytes(body[offset + 2 : offset + 4], "little", signed=False) & 0x7FFF
        if raw_id != raster_id:
            return (
                layer_index,
                raster_id,
                f"source bytes identify raster {raw_id}, not {raster_id}, at 0x{offset:X}",
            )
    return None


def _verify_raster_provenance(path: Path | str, section: str, layers) -> None:
    raster_layers = [layer for layer in layers if bool(layer.get("is_raster_logo"))]
    if not raster_layers:
        return
    decoder, _renderer = _load_backend()
    try:
        payload = decoder.unwrap_forza_container(Path(path))
        body, _counts, _meta = decoder.extract_livery_payload(payload)
    except Exception as exc:
        raise LiveryPreviewError(
            f"정확 미리보기 중단: {section} 영역의 raster 원본 위치를 재검증하지 못했습니다: {exc}"
        ) from exc
    failure = _raster_provenance_failure(decoder, body, raster_layers)
    if failure is None:
        return
    layer_index, raster_id, reason = failure
    raster_text = "알 수 없음" if raster_id is None else str(raster_id)
    raise LiveryPreviewError(
        f"정확 미리보기 중단: {section} 영역의 raster 판정이 원본 C_livery와 일치하지 않습니다. "
        f"raster layer {layer_index}, ID {raster_text}: {reason}. "
        "Decals.zip 누락이 아니라 decoder 구조 해석 오류로 처리합니다."
    )


def verify_section_integrity(path: Path | str, section: str) -> None:
    analysis = analyze_livery_file(path)
    decoded = decode_livery_preview(path)
    failure = _integrity_failure_for_section(analysis.section_counts, decoded.sections, section)
    if failure is not None:
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

    _verify_raster_provenance(path, section, decoded.sections.get(section, ()))


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
