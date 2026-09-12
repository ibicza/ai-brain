from __future__ import annotations

from pathlib import Path

from ai_brain.stage3.acquisition import m336k5_resources as resources
from ai_brain.stage3.acquisition.m336k5_resources import (
    M336K5ResourceMonitor,
    allocate_m336k5_storage_reservation,
    build_m336k5_resource_budget_receipt,
    release_m336k5_storage_reservation,
)


def test_windows_allocated_size_preserves_unsigned_low_word() -> None:
    assert resources._windows_size_words(-0x80000000, 0) == 0x80000000


def test_resource_monitor_is_hash_chained(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    (private / "sample.bin").write_bytes(b"sample")
    monitor = M336K5ResourceMonitor(
        ledger=tmp_path / "resources.jsonl",
        filesystem_root=tmp_path,
        private_root=private,
        temp_root=tmp_path / "temp",
        interval_seconds=1,
    )
    first = monitor.sample("PHASE_A_BEFORE")
    second = monitor.sample("PHASE_A_AFTER")
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_sample_hash == first.sample_hash
    restored = M336K5ResourceMonitor(
        ledger=tmp_path / "resources.jsonl",
        filesystem_root=tmp_path,
        private_root=private,
        temp_root=tmp_path / "temp",
        interval_seconds=1,
    )
    assert restored.samples == (first, second)
    budget = build_m336k5_resource_budget_receipt(
        restored.samples, frozen_storage_budget_bytes=1
    )
    assert budget.sample_count == 2
    assert budget.sample_chain_hash == second.sample_hash


def test_small_storage_reservation_is_real_and_releasable(tmp_path: Path) -> None:
    path = tmp_path / "reservation.bin"
    receipt = allocate_m336k5_storage_reservation(path, reservation_bytes=1024 * 1024)
    assert receipt.status == "PASS"
    assert receipt.sparse is False
    assert path.stat().st_size == 1024 * 1024
    release_m336k5_storage_reservation(path)
    assert not path.exists()
