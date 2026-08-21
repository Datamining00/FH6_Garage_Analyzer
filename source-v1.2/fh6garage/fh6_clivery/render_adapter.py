from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .container import CliveryDecodeError
from .decoder import SECTION_NAMES, decode_clivery_file
from .flatten import FlattenError, FlattenedLivery, flatten_livery_scene
from .livery_sections import LiverySectionDecodeError


RENDER_ADAPTER_FORMAT_ID = "fh6-assistant-independent-render-bridge-v1"
_RASTER_TYPE_WORD_FLAG = 0x8000


class IndependentRenderAdapterError(ValueError):
    """Raised when independent semantics are not yet safe to bind to the renderer."""


@dataclass(frozen=True)
class IndependentRendererScene:
    car_id: int
    sections: dict[str, tuple[dict[str, Any], ...]]
    total_layers: int
    source_format: str = RENDER_ADAPTER_FORMAT_ID


def _validate_vector_word(type_word: int, section: str, source_offset: int) -> None:
    if not 0 < int(type_word) <= 0xFFFF:
        raise IndependentRenderAdapterError(
            f"{section}: invalid FH6 shape word {int(type_word)!r} at 0x{int(source_offset):X}"
        )
    if int(type_word) & _RASTER_TYPE_WORD_FLAG:
        # KFPS/public reverse-engineering evidence indicates the high bit is used
        # by built-in raster/logo placements, but independent M4 raster semantics
        # have not yet been black-box validated. Fail closed rather than treating
        # the record as an ordinary vector Shape.
        raise IndependentRenderAdapterError(
            f"{section}: raster/logo-like type word 0x{int(type_word):04X} at "
            f"0x{int(source_offset):X} is outside the validated independent renderer bridge"
        )


def renderer_scene_from_flattened(flattened: FlattenedLivery) -> IndependentRendererScene:
    """Bind exact independent vector semantics to the existing renderer contract.

    This adapter does not import KFPS or a renderer. It only converts the neutral
    M4 flattened records into the dictionary contract already consumed by the
    FH6 Assistant native-resource renderer. Structural DFS order is preserved.
    """

    names = tuple(section.name for section in flattened.sections)
    if names != tuple(SECTION_NAMES):
        raise IndependentRenderAdapterError(
            "independent renderer bridge requires the complete 11-section C_livery scene"
        )

    output: dict[str, tuple[dict[str, Any], ...]] = {}
    total_layers = 0
    for section in flattened.sections:
        if not section.complete:
            raise IndependentRenderAdapterError(
                f"{section.name}: independent scene is incomplete and cannot drive the renderer"
            )
        if section.flattened_count != section.declared_count:
            raise IndependentRenderAdapterError(
                f"{section.name}: declared {section.declared_count} placements but independent "
                f"flatten produced {section.flattened_count}"
            )

        items: list[dict[str, Any]] = []
        for expected_index, layer in enumerate(section.layers):
            if int(layer.traversal_index) != expected_index:
                raise IndependentRenderAdapterError(
                    f"{section.name}: structural traversal index is discontinuous at "
                    f"{expected_index} ({layer.traversal_index})"
                )
            _validate_vector_word(layer.type_word, section.name, layer.source_offset)
            item = layer.to_dict()
            # Keep the renderer-facing source explicit so diagnostics cannot
            # confuse this path with the pinned legacy KFPS decoder.
            item["source_format"] = RENDER_ADAPTER_FORMAT_ID
            items.append(item)

        output[section.name] = tuple(items)
        total_layers += len(items)

    return IndependentRendererScene(
        car_id=int(flattened.car_id),
        sections=output,
        total_layers=total_layers,
    )


def decode_clivery_renderer_scene(path: Path | str) -> IndependentRendererScene:
    """Decode one C_livery through the independent exact vector bridge.

    Unsupported or unresolved semantics are normalized to one adapter exception
    so the application layer can choose an explicit legacy fallback policy.
    """

    source = Path(path)
    try:
        scene = decode_clivery_file(source)
        flattened = flatten_livery_scene(scene)
        return renderer_scene_from_flattened(flattened)
    except IndependentRenderAdapterError:
        raise
    except (CliveryDecodeError, LiverySectionDecodeError, FlattenError, OSError, ValueError) as exc:
        raise IndependentRenderAdapterError(str(exc)) from exc
