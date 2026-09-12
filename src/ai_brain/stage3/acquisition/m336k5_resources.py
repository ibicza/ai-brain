"""Hash-chained RAM and storage monitoring for M-33.6k.5."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Self

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError

GIB = 1024**3
M336K5_MINIMUM_AVAILABLE_RAM = 2 * GIB
M336K5_MINIMUM_PRIVATE_STORAGE = 24 * GIB
M336K5_MINIMUM_POST_RESERVATION_STORAGE = 8 * GIB
M336K5_MINIMUM_FREE_INODES = 200_000


@dataclass(frozen=True)
class M336K5ResourceSample:
    schema_version: int
    contract_role: str
    sequence: int
    phase: str
    monotonic_ns: int
    system_available_ram_bytes: int
    system_used_ram_bytes: int
    swap_used_bytes: int
    process_tree_rss_bytes: int
    process_tree_peak_rss_bytes: int
    filesystem_identity_hash: str
    filesystem_free_bytes: int
    filesystem_free_inodes: int
    private_root_size_bytes: int
    temp_root_size_bytes: int
    active_task_worker_count: int
    previous_sample_hash: str | None
    sample_hash: str

    def _body(self) -> dict:
        value = asdict(self)
        value.pop("sample_hash")
        return value

    def canonical_object(self) -> dict:
        return {**self._body(), "sample_hash": self.sample_hash}

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K5 resource sample fields changed")
        sample = cls(**value)
        if (
            sample.schema_version != 1
            or sample.contract_role != "M336K5_PRIVATE_RESOURCE_SAMPLE"
            or sample.sequence < 1
            or sample.monotonic_ns < 0
            or any(
                item < 0
                for item in (
                    sample.system_available_ram_bytes,
                    sample.system_used_ram_bytes,
                    sample.swap_used_bytes,
                    sample.process_tree_rss_bytes,
                    sample.process_tree_peak_rss_bytes,
                    sample.filesystem_free_bytes,
                    sample.filesystem_free_inodes,
                    sample.private_root_size_bytes,
                    sample.temp_root_size_bytes,
                    sample.active_task_worker_count,
                )
            )
            or content_hash(sample._body()) != sample.sample_hash
        ):
            raise M336K2ProtocolError("M336K5 resource sample is invalid")
        return sample


@dataclass(frozen=True)
class M336K5ResourceBudgetReceipt:
    schema_version: int
    contract_role: str
    sample_count: int
    sample_chain_hash: str
    maximum_observed_process_tree_peak_rss_bytes: int
    minimum_observed_available_ram_bytes: int
    required_pre_f30_available_ram_bytes: int
    frozen_official_storage_budget_bytes: int
    required_pre_f30_private_storage_bytes: int
    minimum_observed_private_storage_free_bytes: int
    minimum_observed_free_inodes: int
    required_free_inodes: int
    required_post_reservation_storage_bytes: int
    memory_budget_status: str
    storage_budget_status: str
    inode_budget_status: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336K5StorageReservationReceipt:
    schema_version: int
    contract_role: str
    reservation_bytes: int
    reservation_content_hash: str
    filesystem_identity_hash: str
    free_bytes_before: int
    free_bytes_after: int
    allocated_size_bytes: int
    minimum_post_reservation_free_bytes: int
    sparse: bool
    status: str
    receipt_hash: str


class M336K5ResourceMonitor:
    """Write private samples while exposing only aggregate public receipts."""

    def __init__(
        self,
        *,
        ledger: Path,
        filesystem_root: Path,
        private_root: Path,
        temp_root: Path,
        interval_seconds: int = 60,
    ) -> None:
        if not 1 <= interval_seconds <= 60:
            raise ValueError("M336K5 sample interval must be within 1..60 seconds")
        self._ledger = ledger.resolve(strict=False)
        self._filesystem_root = filesystem_root.resolve(strict=True)
        self._private_root = private_root.resolve(strict=False)
        self._temp_root = temp_root.resolve(strict=False)
        self._interval_seconds = interval_seconds
        self._samples: list[M336K5ResourceSample] = []
        self._peak_rss = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._phase = "INITIAL"
        self._lock = threading.Lock()
        if self._ledger.exists():
            self._load_existing()

    @property
    def samples(self) -> tuple[M336K5ResourceSample, ...]:
        return tuple(self._samples)

    def sample(self, phase: str) -> M336K5ResourceSample:
        if not phase or any(character in phase for character in "\r\n\0"):
            raise ValueError("M336K5 resource phase is invalid")
        with self._lock:
            available, used, swap = _system_memory()
            rss, worker_count = _process_tree_memory(os.getpid())
            self._peak_rss = max(self._peak_rss, rss)
            disk = shutil.disk_usage(self._filesystem_root)
            free_inodes = _free_inodes(self._filesystem_root)
            body = {
                "schema_version": 1,
                "contract_role": "M336K5_PRIVATE_RESOURCE_SAMPLE",
                "sequence": len(self._samples) + 1,
                "phase": phase,
                "monotonic_ns": time.monotonic_ns(),
                "system_available_ram_bytes": available,
                "system_used_ram_bytes": used,
                "swap_used_bytes": swap,
                "process_tree_rss_bytes": rss,
                "process_tree_peak_rss_bytes": self._peak_rss,
                "filesystem_identity_hash": _filesystem_identity(self._filesystem_root),
                "filesystem_free_bytes": disk.free,
                "filesystem_free_inodes": free_inodes,
                "private_root_size_bytes": _tree_size(self._private_root),
                "temp_root_size_bytes": _tree_size(self._temp_root),
                "active_task_worker_count": worker_count,
                "previous_sample_hash": self._samples[-1].sample_hash
                if self._samples
                else None,
            }
            sample = M336K5ResourceSample(**body, sample_hash=content_hash(body))
            self._append(sample)
            self._samples.append(sample)
            self._phase = phase
            return sample

    def start(self, phase: str) -> None:
        if self._thread is not None:
            raise RuntimeError("M336K5 resource monitor is already running")
        self.sample(f"{phase}_BEFORE")
        self._phase = phase
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="m336k5-resource-monitor", daemon=True
        )
        self._thread.start()

    def stop(self, phase: str) -> M336K5ResourceSample:
        if self._thread is None:
            raise RuntimeError("M336K5 resource monitor is not running")
        self._stop.set()
        self._thread.join(timeout=self._interval_seconds + 5)
        if self._thread.is_alive():
            raise RuntimeError("M336K5 resource monitor did not stop")
        self._thread = None
        return self.sample(f"{phase}_AFTER")

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            self.sample(f"{self._phase}_PERIODIC")

    def _append(self, sample: M336K5ResourceSample) -> None:
        self._ledger.parent.mkdir(parents=True, exist_ok=True)
        with self._ledger.open("ab") as stream:
            stream.write((canonical_json(sample.canonical_object()) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())

    def _load_existing(self) -> None:
        raw = self._ledger.read_bytes()
        if b"\r" in raw or (raw and not raw.endswith(b"\n")):
            raise M336K2ProtocolError("M336K5 resource ledger is not canonical")
        previous = None
        for line in raw.splitlines():
            sample = M336K5ResourceSample.from_dict(json.loads(line))
            if (
                sample.sequence != len(self._samples) + 1
                or sample.previous_sample_hash != previous
            ):
                raise M336K2ProtocolError("M336K5 resource ledger chain changed")
            self._samples.append(sample)
            self._peak_rss = max(self._peak_rss, sample.process_tree_peak_rss_bytes)
            previous = sample.sample_hash


def build_m336k5_resource_budget_receipt(
    samples: tuple[M336K5ResourceSample, ...], *, frozen_storage_budget_bytes: int
) -> M336K5ResourceBudgetReceipt:
    if not samples or frozen_storage_budget_bytes <= 0:
        raise ValueError("M336K5 resource budget inputs are empty")
    previous = None
    for index, sample in enumerate(samples, start=1):
        M336K5ResourceSample.from_dict(sample.canonical_object())
        if sample.sequence != index or sample.previous_sample_hash != previous:
            raise M336K2ProtocolError("M336K5 resource samples are not one chain")
        previous = sample.sample_hash
    peak = max(item.process_tree_peak_rss_bytes for item in samples)
    required_ram = max(M336K5_MINIMUM_AVAILABLE_RAM, (3 * peak + 1) // 2 + GIB)
    required_storage = max(
        M336K5_MINIMUM_PRIVATE_STORAGE, frozen_storage_budget_bytes + 8 * GIB
    )
    minimum_ram = min(item.system_available_ram_bytes for item in samples)
    minimum_storage = min(item.filesystem_free_bytes for item in samples)
    inode_values = tuple(
        item.filesystem_free_inodes
        for item in samples
        if item.filesystem_free_inodes > 0
    )
    minimum_inodes = min(inode_values) if inode_values else 0
    memory_status = "PASS" if minimum_ram >= required_ram else "FAIL"
    storage_status = "PASS" if minimum_storage >= required_storage else "FAIL"
    inode_status = (
        "PASS"
        if not inode_values or minimum_inodes >= M336K5_MINIMUM_FREE_INODES
        else "FAIL"
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K5_RESOURCE_BUDGET_RECEIPT",
        "sample_count": len(samples),
        "sample_chain_hash": samples[-1].sample_hash,
        "maximum_observed_process_tree_peak_rss_bytes": peak,
        "minimum_observed_available_ram_bytes": minimum_ram,
        "required_pre_f30_available_ram_bytes": required_ram,
        "frozen_official_storage_budget_bytes": frozen_storage_budget_bytes,
        "required_pre_f30_private_storage_bytes": required_storage,
        "minimum_observed_private_storage_free_bytes": minimum_storage,
        "minimum_observed_free_inodes": minimum_inodes,
        "required_free_inodes": M336K5_MINIMUM_FREE_INODES,
        "required_post_reservation_storage_bytes": (
            M336K5_MINIMUM_POST_RESERVATION_STORAGE
        ),
        "memory_budget_status": memory_status,
        "storage_budget_status": storage_status,
        "inode_budget_status": inode_status,
        "status": (
            "PASS"
            if memory_status == storage_status == inode_status == "PASS"
            else "FAIL"
        ),
    }
    return M336K5ResourceBudgetReceipt(**body, receipt_hash=content_hash(body))


def allocate_m336k5_storage_reservation(
    path: Path, *, reservation_bytes: int
) -> M336K5StorageReservationReceipt:
    destination = path.resolve(strict=False)
    if reservation_bytes <= 0 or destination.exists():
        raise ValueError("M336K5 storage reservation target is invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = shutil.disk_usage(destination.parent).free
    digest = hashlib.sha256()
    remaining = reservation_bytes
    with destination.open("xb", buffering=0) as stream:
        while remaining:
            chunk = os.urandom(min(8 * 1024 * 1024, remaining))
            stream.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        os.fsync(stream.fileno())
    after = shutil.disk_usage(destination.parent).free
    allocated = _allocated_size(destination)
    sparse = allocated < reservation_bytes
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K5_STORAGE_RESERVATION_RECEIPT",
        "reservation_bytes": reservation_bytes,
        "reservation_content_hash": digest.hexdigest(),
        "filesystem_identity_hash": _filesystem_identity(destination.parent),
        "free_bytes_before": before,
        "free_bytes_after": after,
        "allocated_size_bytes": allocated,
        "minimum_post_reservation_free_bytes": (
            M336K5_MINIMUM_POST_RESERVATION_STORAGE
        ),
        "sparse": sparse,
        "status": (
            "PASS"
            if not sparse
            and destination.stat().st_size == reservation_bytes
            and after >= M336K5_MINIMUM_POST_RESERVATION_STORAGE
            else "FAIL"
        ),
    }
    receipt = M336K5StorageReservationReceipt(**body, receipt_hash=content_hash(body))
    if receipt.status != "PASS":
        raise M336K2ProtocolError("M336K5 storage reservation failed")
    return receipt


def release_m336k5_storage_reservation(path: Path) -> None:
    target = path.resolve(strict=True)
    if not target.is_file():
        raise ValueError("M336K5 storage reservation is not a file")
    target.unlink()
    _fsync_directory(target.parent)


def _tree_size(root: Path) -> int:
    if not root.exists():
        return 0
    if root.is_file():
        return root.stat().st_size
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except FileNotFoundError:
                        continue
        except FileNotFoundError:
            continue
    return total


def _filesystem_identity(root: Path) -> str:
    resolved = root.resolve(strict=True)
    anchor = resolved.anchor or str(resolved)
    return hashlib.sha256(os.path.normcase(anchor).encode("utf-8")).hexdigest()


def _free_inodes(root: Path) -> int:
    if os.name == "nt":
        return 0
    value = os.statvfs(root)
    return int(value.f_favail)


def _allocated_size(path: Path) -> int:
    stat = path.stat()
    blocks = getattr(stat, "st_blocks", None)
    if blocks is not None:
        return int(blocks) * 512
    if os.name != "nt":
        return stat.st_size
    high = ctypes.c_ulong(0)
    low = int(
        ctypes.windll.kernel32.GetCompressedFileSizeW(str(path), ctypes.byref(high))
    )
    if (low & 0xFFFFFFFF) == 0xFFFFFFFF and ctypes.GetLastError() != 0:
        raise OSError(ctypes.GetLastError(), "GetCompressedFileSizeW failed")
    return _windows_size_words(low, int(high.value))


def _windows_size_words(low: int, high: int) -> int:
    return ((high & 0xFFFFFFFF) << 32) | (low & 0xFFFFFFFF)


def _system_memory() -> tuple[int, int, int]:
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        value = MemoryStatus()
        value.length = ctypes.sizeof(value)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            raise OSError("GlobalMemoryStatusEx failed")
        used = int(value.total_physical - value.available_physical)
        swap = max(
            0,
            int(value.total_page_file - value.available_page_file) - used,
        )
        return int(value.available_physical), used, swap
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        name, raw = line.split(":", 1)
        values[name] = int(raw.strip().split()[0]) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    swap = values.get("SwapTotal", 0) - values.get("SwapFree", 0)
    return available, max(0, total - available), max(0, swap)


def _process_tree_memory(root_pid: int) -> tuple[int, int]:
    if os.name == "nt":
        return _windows_process_tree_memory(root_pid)
    processes: dict[int, tuple[int, int]] = {}
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            fields = (item / "stat").read_text(encoding="ascii").split()
            ppid = int(fields[3])
            rss_pages = int(fields[23])
            processes[int(item.name)] = (ppid, rss_pages * os.sysconf("SC_PAGE_SIZE"))
        except (FileNotFoundError, PermissionError, IndexError, ValueError):
            continue
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _rss) in processes.items():
            if ppid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sum(processes.get(pid, (0, 0))[1] for pid in descendants), len(descendants)


def _windows_process_tree_memory(root_pid: int) -> tuple[int, int]:
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    class MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel = ctypes.windll.kernel32
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("CreateToolhelp32Snapshot failed")
    parents: dict[int, int] = {}
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        success = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            success = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    rss = 0
    count = 0
    for pid in descendants:
        handle = kernel.OpenProcess(0x1000 | 0x0010, False, pid)
        if not handle:
            continue
        try:
            counters = MemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            ):
                rss += int(counters.WorkingSetSize)
                count += 1
        finally:
            kernel.CloseHandle(handle)
    return rss, count


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
