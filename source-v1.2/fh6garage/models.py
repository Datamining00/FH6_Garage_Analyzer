from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class SaveMetadata:
    selected_path: Path
    save_root: Path
    containers_root: Path
    active_version: str = ""
    user_id: str = ""
    game_id: str = ""
    created: str = ""
    last_write: str = ""
    device_id: str = ""
    session_id: str = ""
    package_full_name: str = ""
    save_description: str = ""
    reported_car_count: Optional[int] = None
    play_time: str = ""
    experience: str = ""


@dataclass(slots=True)
class HeaderInfo:
    version: int = 0
    name: str = ""
    description: str = ""
    creator: str = ""
    created: str = ""
    car_id: Optional[int] = None

    # Historical header-tail fields. These values are retained because existing
    # annotations, refresh history and backup metadata may use them as stable
    # local identities even where their original semantic labels were inferred.
    guid: str = ""
    decal_count: Optional[int] = None
    platform_code: Optional[int] = None

    # Structurally verified fields from the creator-relative FH6 livery section.
    # They are additive so existing local state keyed by ``guid`` remains valid.
    asset_guid: str = ""
    type_value: Optional[int] = None

    # CarOrdinal exactly as produced by the header parser before scanner-level
    # container-name recovery. ``car_id`` remains the compatibility/public
    # resolved value used by existing UI, annotations and summaries.
    parsed_car_id: Optional[int] = None


@dataclass(slots=True)
class LiveryRecord:
    container_name: str
    container_path: Path
    kind: str
    header: HeaderInfo
    thumbnail_path: Optional[Path] = None
    livery_path: Optional[Path] = None
    downloaded_at: Optional[float] = None
    content_sha256: str = ""

    @property
    def car_id(self) -> Optional[int]:
        return self.header.car_id


@dataclass(slots=True)
class TuningRecord:
    container_name: str
    container_path: Path
    header: HeaderInfo
    thumbnail_path: Optional[Path] = None
    data_path: Optional[Path] = None
    data_size: int = 0
    downloaded_at: Optional[float] = None

    @property
    def car_id(self) -> Optional[int]:
        return self.header.car_id


@dataclass(slots=True)
class CarName:
    car_id: int
    label: str = ""
    manufacturer: str = ""
    model: str = ""
    source: str = ""


@dataclass(slots=True)
class CarContentSummary:
    car_id: int
    label: str = ""
    livery_count: int = 0
    tuning_count: int = 0
    base_livery_count: int = 0
    soulbound_count: int = 0


@dataclass(slots=True)
class ScanResult:
    metadata: SaveMetadata
    liveries: list[LiveryRecord] = field(default_factory=list)
    tunings: list[TuningRecord] = field(default_factory=list)
    car_summaries: list[CarContentSummary] = field(default_factory=list)
    container_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # Local-only timing/cache data.  It is never read from or written into the
    # FH6 save tree and has no effect on user-facing scan semantics.
    diagnostics: dict[str, object] = field(default_factory=dict)
