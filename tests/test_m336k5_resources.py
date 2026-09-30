from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_resource_budget_uses_post_reservation_storage_floor(
    tmp_path: Path, monkeypatch
) -> None:
    free_bytes = 10 * resources.GIB
    monkeypatch.setattr(
        resources.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=free_bytes),
    )
    monkeypatch.setattr(
        resources,
        "_system_memory",
        lambda: (10 * resources.GIB, resources.GIB, 0),
    )
    monkeypatch.setattr(resources, "_process_tree_memory", lambda _pid: (1, 1))
    monkeypatch.setattr(
        resources,
        "_free_inodes",
        lambda _path: resources.M336K5_MINIMUM_FREE_INODES,
    )
    monitor = M336K5ResourceMonitor(
        ledger=tmp_path / "resources.jsonl",
        filesystem_root=tmp_path,
        private_root=tmp_path / "private",
        temp_root=tmp_path / "temp",
    )
    sample = monitor.sample("POST_RESERVATION")

    budget = build_m336k5_resource_budget_receipt(
        (sample,), frozen_storage_budget_bytes=2 * resources.GIB
    )

    assert budget.required_pre_f30_private_storage_bytes == 24 * resources.GIB
    assert budget.required_post_reservation_storage_bytes == 8 * resources.GIB
    assert budget.minimum_observed_private_storage_free_bytes == free_bytes
    assert budget.storage_budget_status == "PASS"
    assert budget.status == "PASS"


def test_resource_budget_rejects_storage_below_post_reservation_floor(
    tmp_path: Path, monkeypatch
) -> None:
    free_bytes = 7 * resources.GIB
    monkeypatch.setattr(
        resources.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=free_bytes),
    )
    monkeypatch.setattr(
        resources,
        "_system_memory",
        lambda: (10 * resources.GIB, resources.GIB, 0),
    )
    monkeypatch.setattr(resources, "_process_tree_memory", lambda _pid: (1, 1))
    monkeypatch.setattr(
        resources,
        "_free_inodes",
        lambda _path: resources.M336K5_MINIMUM_FREE_INODES,
    )
    monitor = M336K5ResourceMonitor(
        ledger=tmp_path / "resources.jsonl",
        filesystem_root=tmp_path,
        private_root=tmp_path / "private",
        temp_root=tmp_path / "temp",
    )
    sample = monitor.sample("POST_RESERVATION")

    budget = build_m336k5_resource_budget_receipt(
        (sample,), frozen_storage_budget_bytes=2 * resources.GIB
    )

    assert budget.storage_budget_status == "FAIL"
    assert budget.status == "FAIL"
