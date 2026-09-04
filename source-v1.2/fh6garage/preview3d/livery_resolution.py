from __future__ import annotations
from dataclasses import dataclass
NATIVE_CANVAS_SIZE = (2048, 1024)

@dataclass(frozen=True)
class LiveryResolution:
    key: str
    label: str
    width: int
    height: int
    scale: int
    experimental: bool = False

    @property
    def canvas_size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def raw_rgba_bytes(self) -> int:
        return int(self.width) * int(self.height) * 4
_RESOLUTIONS = {'normal': LiveryResolution(key='normal', label='1x Normal (2048 x 1024)', width=2048, height=1024, scale=1), 'high': LiveryResolution(key='high', label='2x High (4096 x 2048)', width=4096, height=2048, scale=2), 'ultra4x': LiveryResolution(key='ultra4x', label='4x Ultra (8192 x 4096)', width=8192, height=4096, scale=4), 'extreme8x': LiveryResolution(key='extreme8x', label='8x Extreme (16384 x 8192)', width=16384, height=8192, scale=8, experimental=True), 'experimental16x': LiveryResolution(key='experimental16x', label='16x Experimental (32768 x 16384)', width=32768, height=16384, scale=16, experimental=True)}

def resolve_livery_resolution(value: str | LiveryResolution | None) -> LiveryResolution:
    if isinstance(value, LiveryResolution):
        return value
    key = str(value or 'normal').strip().casefold()
    try:
        return _RESOLUTIONS[key]
    except KeyError as exc:
        raise ValueError(f'Unsupported livery resolution {value!r}; expected one of ' + ', '.join(sorted(_RESOLUTIONS))) from exc

def available_livery_resolutions() -> tuple[LiveryResolution, ...]:
    return tuple((_RESOLUTIONS[key] for key in ('normal', 'high', 'ultra4x', 'extreme8x', 'experimental16x')))
