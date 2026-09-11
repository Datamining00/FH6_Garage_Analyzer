from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass

_GIB = 1024 ** 3
_MIB = 1024 ** 2


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Conservative hardware policy shared by scan/UI performance features.

    The policy deliberately caps concurrency. FH6 Assistant mostly performs
    many small file reads plus hashing, so unbounded worker counts can make
    HDDs and low-end systems slower while increasing memory pressure.
    """

    cpu_count: int
    physical_memory_bytes: int | None
    scan_workers: int
    pixmap_cache_bytes: int
    parallel_scan_min_items: int = 16
    parallel_scan_min_bytes: int = 64 * _MIB

    def as_dict(self) -> dict[str, int | None]:
        return asdict(self)


def _physical_memory_bytes() -> int | None:
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except Exception:  # noqa: BLE001 - hardware probing must be best-effort
            return None

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        value = int(pages) * int(page_size)
        return value if value > 0 else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _env_int(name: str, minimum: int, maximum: int) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(minimum, min(maximum, value))


def detect_runtime_policy() -> RuntimePolicy:
    """Return a compatibility-first policy that scales from low-end to fast PCs.

    Environment variables are intentionally diagnostic/advanced overrides only:
      * FH6_ASSISTANT_SCAN_WORKERS: 1..8
      * FH6_ASSISTANT_PIXMAP_CACHE_MB: 8..256
    """

    cpu = max(1, int(os.cpu_count() or 1))
    memory = _physical_memory_bytes()

    if cpu <= 2 or (memory is not None and memory <= 4 * _GIB):
        workers = 1
    elif cpu <= 4 or (memory is not None and memory <= 8 * _GIB):
        workers = 2
    elif cpu <= 8:
        workers = 3
    else:
        workers = 4

    override_workers = _env_int("FH6_ASSISTANT_SCAN_WORKERS", 1, 8)
    if override_workers is not None:
        workers = override_workers

    if memory is None:
        pixmap_mb = 64
    elif memory <= 4 * _GIB:
        pixmap_mb = 24
    elif memory <= 8 * _GIB:
        pixmap_mb = 48
    elif memory <= 16 * _GIB:
        pixmap_mb = 96
    else:
        pixmap_mb = 128

    override_cache = _env_int("FH6_ASSISTANT_PIXMAP_CACHE_MB", 8, 256)
    if override_cache is not None:
        pixmap_mb = override_cache

    return RuntimePolicy(
        cpu_count=cpu,
        physical_memory_bytes=memory,
        scan_workers=workers,
        pixmap_cache_bytes=pixmap_mb * _MIB,
    )
