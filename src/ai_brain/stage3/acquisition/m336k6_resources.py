"""Expanded aggregate resource monitoring for M-33.6k.6."""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k5_resources import (
    _filesystem_identity,
    _free_inodes,
    _process_tree_memory,
    _system_memory,
    _tree_size,
)


@dataclass(frozen=True)
class M336K6ResourceSample:
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
    capsule_size_bytes: int
    official_vault_size_bytes: int
    selected_snapshot_size_bytes: int
    production_roots_size_bytes: int
    evaluator_root_size_bytes: int
    active_task_process_count: int
    previous_sample_hash: str | None
    sample_hash: str


class M336K6ResourceMonitor:
    """Sample every required M-33.6k.6 resource without publishing paths."""

    def __init__(
        self,
        *,
        filesystem_root: Path,
        capsule_root: Path,
        official_vault: Path,
        selected_snapshot: Path,
        production_roots: tuple[Path, ...],
        evaluator_root: Path,
    ) -> None:
        self._filesystem_root = filesystem_root.resolve(strict=True)
        self._capsule_root = capsule_root.resolve(strict=False)
        self._official_vault = official_vault.resolve(strict=False)
        self._selected_snapshot = selected_snapshot.resolve(strict=False)
        self._production_roots = tuple(
            item.resolve(strict=False) for item in production_roots
        )
        self._evaluator_root = evaluator_root.resolve(strict=False)
        self._samples: list[M336K6ResourceSample] = []
        self._peak_rss = 0

    @property
    def samples(self) -> tuple[M336K6ResourceSample, ...]:
        return tuple(self._samples)

    def sample(self, phase: str) -> M336K6ResourceSample:
        if not phase or any(character in phase for character in "\r\n\0"):
            raise ValueError("M336K6 resource phase is invalid")
        available, used, swap = _system_memory()
        rss, active = _process_tree_memory(os.getpid())
        self._peak_rss = max(self._peak_rss, rss)
        disk = shutil.disk_usage(self._filesystem_root)
        body = {
            "schema_version": 1,
            "contract_role": "M336K6_PRIVATE_RESOURCE_SAMPLE",
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
            "filesystem_free_inodes": _free_inodes(self._filesystem_root),
            "capsule_size_bytes": _tree_size(self._capsule_root),
            "official_vault_size_bytes": _tree_size(self._official_vault),
            "selected_snapshot_size_bytes": _tree_size(self._selected_snapshot),
            "production_roots_size_bytes": sum(
                _tree_size(item) for item in self._production_roots
            ),
            "evaluator_root_size_bytes": _tree_size(self._evaluator_root),
            "active_task_process_count": active,
            "previous_sample_hash": self._samples[-1].sample_hash
            if self._samples
            else None,
        }
        result = M336K6ResourceSample(**body, sample_hash=content_hash(body))
        self._samples.append(result)
        return result


def build_m336k6_resource_receipt(
    samples: tuple[M336K6ResourceSample, ...],
) -> dict:
    if not samples:
        raise ValueError("M336K6 resource sample set is empty")
    previous = None
    for sequence, sample in enumerate(samples, 1):
        body = asdict(sample)
        claimed = body.pop("sample_hash")
        if (
            sample.sequence != sequence
            or sample.previous_sample_hash != previous
            or content_hash(body) != claimed
        ):
            raise ValueError("M336K6 resource sample chain is invalid")
        previous = sample.sample_hash
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K6_RESOURCE_MONITOR_RECEIPT",
        "sample_count": len(samples),
        "sample_chain_hash": samples[-1].sample_hash,
        "minimum_available_ram_bytes": min(
            item.system_available_ram_bytes for item in samples
        ),
        "maximum_process_tree_peak_rss_bytes": max(
            item.process_tree_peak_rss_bytes for item in samples
        ),
        "maximum_swap_used_bytes": max(item.swap_used_bytes for item in samples),
        "minimum_filesystem_free_bytes": min(
            item.filesystem_free_bytes for item in samples
        ),
        "minimum_filesystem_free_inodes": min(
            item.filesystem_free_inodes for item in samples
        ),
        "maximum_capsule_size_bytes": max(item.capsule_size_bytes for item in samples),
        "maximum_official_vault_size_bytes": max(
            item.official_vault_size_bytes for item in samples
        ),
        "maximum_selected_snapshot_size_bytes": max(
            item.selected_snapshot_size_bytes for item in samples
        ),
        "maximum_production_roots_size_bytes": max(
            item.production_roots_size_bytes for item in samples
        ),
        "maximum_evaluator_root_size_bytes": max(
            item.evaluator_root_size_bytes for item in samples
        ),
        "maximum_active_task_process_count": max(
            item.active_task_process_count for item in samples
        ),
        "status": "PASS",
    }
    return {**body, "receipt_hash": content_hash(body)}
