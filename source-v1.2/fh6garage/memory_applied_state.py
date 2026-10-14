from __future__ import annotations

import concurrent.futures
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .local_storage import write_json_atomic

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x00000002
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE_READWRITE = 0x40
PAGE_EXECUTE_WRITECOPY = 0x80
PAGE_GUARD = 0x100
_ALLOWED_PROTECTIONS = {
    PAGE_READWRITE,
    PAGE_WRITECOPY,
    PAGE_EXECUTE_READWRITE,
    PAGE_EXECUTE_WRITECOPY,
}

GAME_EXE = "forzahorizon6.exe"
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_OVERLAP = 128
DEFAULT_WORKERS = 8
MIN_RECOVERY_BLOCK = 256 * 1024
STATE_SCHEMA = 1

if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:
    _kernel32 = None

ULONG_PTR = ctypes.c_size_t


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ULONG_PTR),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", wt.WCHAR * 260),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", wt.LPVOID),
        ("AllocationBase", wt.LPVOID),
        ("AllocationProtect", wt.DWORD),
        ("PartitionId", wt.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


class _SYSTEM_INFO_HEAD(ctypes.Structure):
    _fields_ = [("wProcessorArchitecture", wt.WORD), ("wReserved", wt.WORD)]


class _SYSTEM_INFO_UNION(ctypes.Union):
    _fields_ = [("dwOemId", wt.DWORD), ("head", _SYSTEM_INFO_HEAD)]


class SYSTEM_INFO(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("u", _SYSTEM_INFO_UNION),
        ("dwPageSize", wt.DWORD),
        ("lpMinimumApplicationAddress", wt.LPVOID),
        ("lpMaximumApplicationAddress", wt.LPVOID),
        ("dwActiveProcessorMask", ULONG_PTR),
        ("dwNumberOfProcessors", wt.DWORD),
        ("dwProcessorType", wt.DWORD),
        ("dwAllocationGranularity", wt.DWORD),
        ("wProcessorLevel", wt.WORD),
        ("wProcessorRevision", wt.WORD),
    ]


def _configure_windows_api() -> None:
    if _kernel32 is None:
        return
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    _kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _kernel32.Process32FirstW.restype = wt.BOOL
    _kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _kernel32.Process32NextW.restype = wt.BOOL
    _kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _kernel32.OpenProcess.restype = wt.HANDLE
    _kernel32.VirtualQueryEx.argtypes = [
        wt.HANDLE,
        wt.LPCVOID,
        ctypes.POINTER(MEMORY_BASIC_INFORMATION),
        ctypes.c_size_t,
    ]
    _kernel32.VirtualQueryEx.restype = ctypes.c_size_t
    _kernel32.ReadProcessMemory.argtypes = [
        wt.HANDLE,
        wt.LPCVOID,
        wt.LPVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    _kernel32.ReadProcessMemory.restype = wt.BOOL
    _kernel32.GetSystemInfo.argtypes = [ctypes.POINTER(SYSTEM_INFO)]
    _kernel32.GetSystemInfo.restype = None
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32.CloseHandle.restype = wt.BOOL


_configure_windows_api()


@dataclass(frozen=True, slots=True)
class Region:
    base: int
    size: int
    protect: int

    @property
    def end(self) -> int:
        return self.base + self.size


@dataclass(frozen=True, slots=True)
class StrictRecord:
    address: int
    livery_name: str
    car_id: int


@dataclass(slots=True)
class ReadStats:
    calls: int = 0
    failures: int = 0
    bytes_read: int = 0
    errors: Counter = field(default_factory=Counter)


@dataclass(slots=True)
class RegionScan:
    region: Region
    records: list[StrictRecord]
    stats: ReadStats


@dataclass(frozen=True, slots=True)
class MemoryScanResult:
    pid: int
    status: str
    active_livery_names: frozenset[str]
    dominant_fingerprint: str = ""
    dominant_regions: tuple[int, ...] = ()
    candidate_regions: int = 0
    read_bytes: int = 0
    read_failures: int = 0
    elapsed_seconds: float = 0.0
    note: str = ""

    @property
    def usable(self) -> bool:
        return self.status in {"HIGH", "MEDIUM"}


@dataclass(frozen=True, slots=True)
class PersistedAppliedState:
    scanned_at: str
    pid: int
    consensus_status: str
    active_livery_names: frozenset[str]
    soulbound_applied_names: frozenset[str] = frozenset()
    soulbound_unapplied_names: frozenset[str] = frozenset()
    soulbound_review_names: frozenset[str] = frozenset()
    dominant_fingerprint: str = ""
    dominant_regions: tuple[int, ...] = ()
    candidate_regions: int = 0
    read_bytes: int = 0
    read_failures: int = 0
    elapsed_seconds: float = 0.0

    @property
    def usable(self) -> bool:
        return self.consensus_status in {"HIGH", "MEDIUM"}

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema": STATE_SCHEMA,
            "scanned_at": self.scanned_at,
            "pid": self.pid,
            "consensus_status": self.consensus_status,
            "active_livery_names": sorted(self.active_livery_names),
            "soulbound_applied_names": sorted(self.soulbound_applied_names),
            "soulbound_unapplied_names": sorted(self.soulbound_unapplied_names),
            "soulbound_review_names": sorted(self.soulbound_review_names),
            "dominant_fingerprint": self.dominant_fingerprint,
            "dominant_regions": list(self.dominant_regions),
            "candidate_regions": self.candidate_regions,
            "read_bytes": self.read_bytes,
            "read_failures": self.read_failures,
            "elapsed_seconds": self.elapsed_seconds,
        }

    @classmethod
    def from_json_dict(cls, data: object) -> "PersistedAppliedState | None":
        if not isinstance(data, dict) or data.get("schema") != STATE_SCHEMA:
            return None
        try:
            status = str(data.get("consensus_status") or "")
            if status not in {"HIGH", "MEDIUM", "AMBIGUOUS", "NONE"}:
                return None
            return cls(
                scanned_at=str(data.get("scanned_at") or ""),
                pid=int(data.get("pid") or 0),
                consensus_status=status,
                active_livery_names=frozenset(str(x) for x in data.get("active_livery_names", [])),
                soulbound_applied_names=frozenset(str(x) for x in data.get("soulbound_applied_names", [])),
                soulbound_unapplied_names=frozenset(str(x) for x in data.get("soulbound_unapplied_names", [])),
                soulbound_review_names=frozenset(str(x) for x in data.get("soulbound_review_names", [])),
                dominant_fingerprint=str(data.get("dominant_fingerprint") or ""),
                dominant_regions=tuple(int(x) for x in data.get("dominant_regions", [])),
                candidate_regions=int(data.get("candidate_regions") or 0),
                read_bytes=int(data.get("read_bytes") or 0),
                read_failures=int(data.get("read_failures") or 0),
                elapsed_seconds=float(data.get("elapsed_seconds") or 0.0),
            )
        except (TypeError, ValueError):
            return None


def default_state_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "FH6GarageAnalyzer" / "memory_applied_state.json"


def save_applied_state(state: PersistedAppliedState, path: Path | None = None) -> bool:
    return write_json_atomic(path or default_state_path(), state.to_json_dict())


def load_applied_state(path: Path | None = None) -> PersistedAppliedState | None:
    target = path or default_state_path()
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return PersistedAppliedState.from_json_dict(payload)


def normalized_livery_name(container_name: str) -> str:
    name = (container_name or "").strip()
    if name.startswith("SoulBoundLivery_"):
        return "Livery_" + name[len("SoulBoundLivery_"):]
    return name if name.startswith("Livery_") else ""


def _require_windows() -> None:
    if os.name != "nt" or _kernel32 is None:
        raise OSError("FH6 memory scan is available on Windows only")


def find_game_pid(exe_name: str = GAME_EXE) -> int | None:
    _require_windows()
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid = ctypes.c_void_p(-1).value
    if not snapshot or snapshot == invalid:
        return None
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        if not _kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None
        while True:
            if entry.szExeFile.casefold() == exe_name.casefold():
                return int(entry.th32ProcessID)
            if not _kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return None
    finally:
        _kernel32.CloseHandle(snapshot)


def _system_address_range() -> tuple[int, int]:
    info = SYSTEM_INFO()
    _kernel32.GetSystemInfo(ctypes.byref(info))
    lower = ctypes.cast(info.lpMinimumApplicationAddress, ctypes.c_void_p).value or 0
    upper = ctypes.cast(info.lpMaximumApplicationAddress, ctypes.c_void_p).value or 0x7FFFFFFFFFFF
    return int(lower), int(upper)


def _read_digits(data: bytes, pos: int, min_len: int, max_len: int) -> tuple[str, int] | None:
    start = pos
    limit = min(len(data), pos + max_len)
    while pos < limit and 48 <= data[pos] <= 57:
        pos += 1
    if pos - start < min_len:
        return None
    return data[start:pos].decode("ascii"), pos


def _read_exact_digits(data: bytes, pos: int, count: int) -> tuple[str, int] | None:
    end = pos + count
    if end > len(data):
        return None
    part = data[pos:end]
    if any(byte < 48 or byte > 57 for byte in part):
        return None
    return part.decode("ascii"), end


def _parse_named_timestamp(data: bytes, pos: int, prefix: bytes) -> tuple[str, int, int] | None:
    if not data.startswith(prefix, pos):
        return None
    cursor = pos + len(prefix)
    car = _read_digits(data, cursor, 3, 6)
    if car is None:
        return None
    car_text, cursor = car
    if cursor >= len(data) or data[cursor] != 0x5F:
        return None
    stamp = _read_exact_digits(data, cursor + 1, 14)
    if stamp is None:
        return None
    _stamp_text, cursor = stamp
    return data[pos:cursor].decode("ascii"), int(car_text), cursor


_HEX = frozenset(b"0123456789abcdefABCDEF")


def _parse_guid(data: bytes, pos: int) -> int | None:
    end = pos + 36
    if end > len(data):
        return None
    part = data[pos:end]
    for index, byte in enumerate(part):
        if index in (8, 13, 18, 23):
            if byte != 0x2D:
                return None
        elif byte not in _HEX:
            return None
    return end


def parse_strict_livery_record(data: bytes, pos: int, absolute_base: int) -> StrictRecord | None:
    livery = _parse_named_timestamp(data, pos, b"Livery_")
    if livery is None:
        return None
    livery_name, car_id, cursor = livery

    tuning = _parse_named_timestamp(data, cursor, b"Tuning_")
    if tuning is not None:
        _tuning_name, tuning_car_id, _ = tuning
        if tuning_car_id != car_id:
            return None
        return StrictRecord(absolute_base + pos, livery_name, car_id)

    if _parse_guid(data, cursor) is not None:
        return StrictRecord(absolute_base + pos, livery_name, car_id)
    return None


def scan_buffer(data: bytes, absolute_base: int) -> list[StrictRecord]:
    records: list[StrictRecord] = []
    start = 0
    while True:
        pos = data.find(b"Livery_", start)
        if pos < 0:
            break
        start = pos + 1
        record = parse_strict_livery_record(data, pos, absolute_base)
        if record is not None:
            records.append(record)
    return records


class ReadOnlyProcessMemory:
    def __init__(self, pid: int):
        _require_windows()
        self.pid = pid
        ctypes.set_last_error(0)
        self.handle = _kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
            False,
            pid,
        )
        if not self.handle:
            raise OSError(f"OpenProcess failed (PID={pid}, WinError={ctypes.get_last_error()})")

    def close(self) -> None:
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "ReadOnlyProcessMemory":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def enumerate_candidate_regions(self) -> list[Region]:
        lower, upper = _system_address_range()
        address = lower
        result: list[Region] = []
        while address < upper:
            mbi = MEMORY_BASIC_INFORMATION()
            got = _kernel32.VirtualQueryEx(
                self.handle,
                ctypes.c_void_p(address),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi),
            )
            if got == 0:
                address += 0x10000
                continue
            base = ctypes.cast(mbi.BaseAddress, ctypes.c_void_p).value or 0
            size = int(mbi.RegionSize)
            if size <= 0:
                address += 0x1000
                continue
            protection = int(mbi.Protect)
            if (
                int(mbi.State) == MEM_COMMIT
                and int(mbi.Type) == MEM_PRIVATE
                and not (protection & PAGE_GUARD)
                and (protection & 0xFF) in _ALLOWED_PROTECTIONS
            ):
                result.append(Region(int(base), size, protection))
            next_address = int(base) + size
            address = next_address if next_address > address else address + 0x1000
        return result

    def read_once(self, address: int, size: int, stats: ReadStats) -> bytes | None:
        stats.calls += 1
        buffer = ctypes.create_string_buffer(size)
        read_count = ctypes.c_size_t(0)
        ctypes.set_last_error(0)
        ok = _kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(read_count),
        )
        if not ok:
            stats.failures += 1
            stats.errors[ctypes.get_last_error()] += 1
            return None
        count = int(read_count.value)
        if count <= 0:
            return None
        stats.bytes_read += count
        return buffer.raw[:count]

    def read_resilient(self, address: int, size: int, stats: ReadStats) -> list[tuple[int, bytes]]:
        data = self.read_once(address, size, stats)
        if data is not None:
            return [(address, data)]
        if size <= MIN_RECOVERY_BLOCK:
            return []
        half = size // 2
        return self.read_resilient(address, half, stats) + self.read_resilient(address + half, size - half, stats)


def _scan_region(reader: ReadOnlyProcessMemory, region: Region, chunk_size: int, overlap: int) -> RegionScan:
    stats = ReadStats()
    by_address: dict[int, StrictRecord] = {}
    step = max(64 * 1024, chunk_size - overlap)
    position = region.base
    while position < region.end:
        size = min(chunk_size, region.end - position)
        for block_address, block in reader.read_resilient(position, size, stats):
            for record in scan_buffer(block, block_address):
                by_address[record.address] = record
        position += step
    return RegionScan(region, sorted(by_address.values(), key=lambda item: item.address), stats)


def _fingerprint(names: Iterable[str]) -> str:
    payload = "\n".join(sorted(set(names))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _consensus(scans: list[RegionScan]) -> tuple[str, frozenset[str], str, tuple[int, ...], str]:
    groups: dict[str, tuple[set[str], list[int]]] = {}
    for scan in scans:
        names = {record.livery_name for record in scan.records}
        if not names:
            continue
        digest = _fingerprint(names)
        if digest not in groups:
            groups[digest] = (names, [])
        groups[digest][1].append(scan.region.base)

    if not groups:
        return "NONE", frozenset(), "", (), "No strict livery snapshot was found"

    ranked = sorted(
        ((len(names), len(regions), digest, names, regions) for digest, (names, regions) in groups.items()),
        reverse=True,
    )
    largest_count = ranked[0][0]
    largest = [item for item in ranked if item[0] == largest_count]
    if len(largest) != 1:
        return "AMBIGUOUS", frozenset(), "", (), "Different maximum-size snapshots were observed"

    _count, copies, digest, names, regions = largest[0]
    status = "HIGH" if copies >= 2 else "MEDIUM"
    note = "Repeated identical snapshot" if status == "HIGH" else "Single maximum snapshot"
    return status, frozenset(names), digest, tuple(sorted(regions)), note


def scan_applied_liveries(
    *,
    progress: Callable[[int, int, int, int, float], None] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    workers: int = DEFAULT_WORKERS,
) -> MemoryScanResult:
    """Read FH6 memory only and return the stable current-livery snapshot.

    No process-memory write API, injection, hook, debugger attach, or game-file
    modification is used by this module.
    """
    pid = find_game_pid()
    if pid is None:
        raise ProcessLookupError("Forza Horizon 6 is not running")

    started = time.monotonic()
    with ReadOnlyProcessMemory(pid) as reader:
        regions = reader.enumerate_candidate_regions()
        scans: list[RegionScan] = []
        finished = 0
        bytes_read = 0
        failures = 0
        total = len(regions)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(_scan_region, reader, region, chunk_size, overlap) for region in regions]
            for future in concurrent.futures.as_completed(futures):
                scan = future.result()
                scans.append(scan)
                finished += 1
                bytes_read += scan.stats.bytes_read
                failures += scan.stats.failures
                if progress is not None:
                    progress(finished, total, bytes_read, failures, time.monotonic() - started)

    status, names, digest, dominant_regions, note = _consensus(scans)
    return MemoryScanResult(
        pid=pid,
        status=status,
        active_livery_names=names,
        dominant_fingerprint=digest,
        dominant_regions=dominant_regions,
        candidate_regions=len(regions),
        read_bytes=bytes_read,
        read_failures=failures,
        elapsed_seconds=time.monotonic() - started,
        note=note,
    )


def build_persisted_state(
    result: MemoryScanResult,
    *,
    soulbound_applied_names: Iterable[str] = (),
    soulbound_unapplied_names: Iterable[str] = (),
    soulbound_review_names: Iterable[str] = (),
) -> PersistedAppliedState:
    return PersistedAppliedState(
        scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        pid=result.pid,
        consensus_status=result.status,
        active_livery_names=result.active_livery_names,
        soulbound_applied_names=frozenset(soulbound_applied_names),
        soulbound_unapplied_names=frozenset(soulbound_unapplied_names),
        soulbound_review_names=frozenset(soulbound_review_names),
        dominant_fingerprint=result.dominant_fingerprint,
        dominant_regions=result.dominant_regions,
        candidate_regions=result.candidate_regions,
        read_bytes=result.read_bytes,
        read_failures=result.read_failures,
        elapsed_seconds=result.elapsed_seconds,
    )
