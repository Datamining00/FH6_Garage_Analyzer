from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Protocol, TypeVar


@dataclass(frozen=True, slots=True)
class ScanJob:
    container: Path
    kind: str
    estimated_bytes: int = 0


T = TypeVar("T")


class ScanBackend(Protocol, Generic[T]):
    name: str
    workers: int

    def run(self, jobs: Sequence[ScanJob], analyze: Callable[[ScanJob], T]) -> list[T]:
        ...


@dataclass(frozen=True, slots=True)
class SequentialScanBackend(Generic[T]):
    name: str = "sequential"
    workers: int = 1

    def run(self, jobs: Sequence[ScanJob], analyze: Callable[[ScanJob], T]) -> list[T]:
        return [analyze(job) for job in jobs]


@dataclass(frozen=True, slots=True)
class ThreadedScanBackend(Generic[T]):
    workers: int
    name: str = "threaded-io"

    def run(self, jobs: Sequence[ScanJob], analyze: Callable[[ScanJob], T]) -> list[T]:
        # executor.map preserves input order.  Deterministic container ordering
        # and warning ordering therefore remain identical to the fallback path.
        with ThreadPoolExecutor(
            max_workers=max(1, int(self.workers)),
            thread_name_prefix="fh6-scan",
        ) as executor:
            return list(executor.map(analyze, jobs))
