"""Private-storage planning and public capacity receipts for M-33.6j."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash

GIB = 1024**3
M336J_MINIMUM_FREE_BYTES = 8 * GIB
M336J_QUALIFICATION_FREE_BYTES = 12 * GIB
M336J_MINIMUM_FREE_INODES = 100_000
M336J_MAXIMUM_PATH_LENGTH = 240


class M336JInsufficientPrivateStorage(RuntimeError):
    """No private candidate root satisfies the frozen capacity plan."""


@dataclass(frozen=True)
class KarinaPrivateStoragePlan:
    schema_version: int
    candidate_roots: tuple[Path, ...]
    maximum_expected_transfer_bytes: int
    selected_snapshot_capacity_bytes: int
    vault_capacity_bytes: int
    private_replay_capacity_bytes: int
    compiler_temporary_capacity_bytes: int
    public_production_temporary_capacity_bytes: int
    safety_reserve_bytes: int
    maximum_path_length: int
    required_free_bytes: int
    plan_hash: str


@dataclass(frozen=True)
class KarinaPrivateStorageCapacityReceipt:
    schema_version: int
    contract_role: str
    capacity_class: str
    required_free_bytes: int
    available_free_bytes: int
    available_free_inodes: int
    filesystem_identity_hash: str
    writable: bool
    atomic_rename: bool
    fsync: bool
    root_outside_worktrees: bool
    root_not_symlinked_into_worktree: bool
    maximum_path_length: int
    selected_snapshot_capacity_bytes: int
    vault_capacity_bytes: int
    private_replay_capacity_bytes: int
    compiler_temporary_capacity_bytes: int
    public_production_temporary_capacity_bytes: int
    safety_reserve_bytes: int
    selected_storage_plan_hash: str
    status: str
    receipt_hash: str


def build_private_storage_plan(
    candidate_roots: tuple[Path, ...],
    *,
    maximum_expected_transfer_bytes: int,
    qualification_margin: bool = False,
) -> KarinaPrivateStoragePlan:
    """Freeze artifact capacities without exposing candidate paths publicly."""

    if not candidate_roots or maximum_expected_transfer_bytes <= 0:
        raise ValueError(
            "M336J private storage candidates or transfer bound are invalid"
        )
    if len({str(path) for path in candidate_roots}) != len(candidate_roots):
        raise ValueError("M336J private storage candidates contain duplicates")
    base_required = max(
        M336J_MINIMUM_FREE_BYTES,
        4 * maximum_expected_transfer_bytes + 2 * GIB,
    )
    required = max(
        base_required,
        M336J_QUALIFICATION_FREE_BYTES if qualification_margin else 0,
    )
    public_body = {
        "schema_version": 1,
        "candidate_root_identity_hashes": tuple(
            content_hash(str(path)) for path in candidate_roots
        ),
        "maximum_expected_transfer_bytes": maximum_expected_transfer_bytes,
        "selected_snapshot_capacity_bytes": maximum_expected_transfer_bytes,
        "vault_capacity_bytes": maximum_expected_transfer_bytes,
        "private_replay_capacity_bytes": maximum_expected_transfer_bytes,
        "compiler_temporary_capacity_bytes": maximum_expected_transfer_bytes,
        "public_production_temporary_capacity_bytes": maximum_expected_transfer_bytes,
        "safety_reserve_bytes": required - 4 * maximum_expected_transfer_bytes,
        "maximum_path_length": M336J_MAXIMUM_PATH_LENGTH,
        "required_free_bytes": required,
    }
    return KarinaPrivateStoragePlan(
        schema_version=1,
        candidate_roots=candidate_roots,
        maximum_expected_transfer_bytes=maximum_expected_transfer_bytes,
        selected_snapshot_capacity_bytes=maximum_expected_transfer_bytes,
        vault_capacity_bytes=maximum_expected_transfer_bytes,
        private_replay_capacity_bytes=maximum_expected_transfer_bytes,
        compiler_temporary_capacity_bytes=maximum_expected_transfer_bytes,
        public_production_temporary_capacity_bytes=maximum_expected_transfer_bytes,
        safety_reserve_bytes=public_body["safety_reserve_bytes"],
        maximum_path_length=M336J_MAXIMUM_PATH_LENGTH,
        required_free_bytes=required,
        plan_hash=content_hash(public_body),
    )


def preflight_private_storage(
    plan: KarinaPrivateStoragePlan,
    *,
    git_worktrees: tuple[Path, ...],
) -> KarinaPrivateStorageCapacityReceipt:
    """Select the first safe root and prove capacity, fsync, and atomic rename."""

    _verify_plan(plan)
    worktrees = tuple(path.resolve(strict=True) for path in git_worktrees)
    observations = []
    for candidate in plan.candidate_roots:
        try:
            observation = _probe_candidate(candidate, plan=plan, worktrees=worktrees)
        except (OSError, ValueError):
            continue
        observations.append(observation)
        if observation["status"] == "PASS":
            receipt = KarinaPrivateStorageCapacityReceipt(**observation)
            verify_capacity_receipt(receipt, expected_plan_hash=plan.plan_hash)
            return receipt
    available = max(
        (int(item["available_free_bytes"]) for item in observations), default=0
    )
    raise M336JInsufficientPrivateStorage(
        "PRE_FREEZE_BLOCKED_INSUFFICIENT_PRIVATE_STORAGE: "
        f"required={plan.required_free_bytes} available={available}"
    )


def verify_capacity_receipt(
    receipt: KarinaPrivateStorageCapacityReceipt,
    *,
    expected_plan_hash: str,
) -> None:
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if (
        receipt.schema_version != 1
        or receipt.contract_role != "PUBLIC_M336J_KARINA_STORAGE_CAPACITY_RECEIPT"
        or receipt.selected_storage_plan_hash != expected_plan_hash
        or receipt.available_free_bytes < receipt.required_free_bytes
        or receipt.available_free_inodes < M336J_MINIMUM_FREE_INODES
        or not all(
            (
                receipt.writable,
                receipt.atomic_rename,
                receipt.fsync,
                receipt.root_outside_worktrees,
                receipt.root_not_symlinked_into_worktree,
            )
        )
        or receipt.maximum_path_length != M336J_MAXIMUM_PATH_LENGTH
        or receipt.status != "PASS"
        or content_hash(body) != claimed
    ):
        raise ValueError("M336J private storage capacity receipt is invalid")


def _verify_plan(plan: KarinaPrivateStoragePlan) -> None:
    expected = build_private_storage_plan(
        plan.candidate_roots,
        maximum_expected_transfer_bytes=plan.maximum_expected_transfer_bytes,
        qualification_margin=plan.required_free_bytes >= M336J_QUALIFICATION_FREE_BYTES,
    )
    if expected != plan:
        raise ValueError("M336J private storage plan is not content-derived")


def _probe_candidate(
    candidate: Path,
    *,
    plan: KarinaPrivateStoragePlan,
    worktrees: tuple[Path, ...],
) -> dict:
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ValueError("M336J private storage root is not an absolute physical path")
    root = candidate.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("M336J private storage root is not a directory")
    outside = not any(root == tree or root.is_relative_to(tree) for tree in worktrees)
    reverse_outside = not any(tree.is_relative_to(root) for tree in worktrees)
    no_link_into_worktree = outside and reverse_outside
    if not no_link_into_worktree:
        raise ValueError("M336J private storage intersects a Git worktree")
    usage = shutil.disk_usage(root)
    vfs = os.statvfs(root)
    filesystem_identity = content_hash(
        {
            "device": root.stat().st_dev,
            "fragment_size": vfs.f_frsize,
            "block_size": vfs.f_bsize,
        }
    )
    writable = atomic = synced = False
    with tempfile.TemporaryDirectory(prefix="m336j-storage-probe-", dir=root) as raw:
        probe = Path(raw)
        if len(str(probe / ("x" * 32))) > plan.maximum_path_length:
            raise ValueError("M336J private storage path policy would be exceeded")
        first = probe / "probe.incoming"
        final = probe / "probe.final"
        with first.open("wb") as handle:
            handle.write(b"m336j-private-storage-probe\n")
            handle.flush()
            os.fsync(handle.fileno())
            writable = True
        os.replace(first, final)
        atomic = final.is_file()
        descriptor = os.open(probe, os.O_RDONLY)
        try:
            os.fsync(descriptor)
            synced = True
        finally:
            os.close(descriptor)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_M336J_KARINA_STORAGE_CAPACITY_RECEIPT",
        "capacity_class": (
            "AT_LEAST_12_GIB"
            if usage.free >= M336J_QUALIFICATION_FREE_BYTES
            else "AT_LEAST_8_GIB"
        ),
        "required_free_bytes": plan.required_free_bytes,
        "available_free_bytes": usage.free,
        "available_free_inodes": vfs.f_favail,
        "filesystem_identity_hash": filesystem_identity,
        "writable": writable,
        "atomic_rename": atomic,
        "fsync": synced,
        "root_outside_worktrees": outside,
        "root_not_symlinked_into_worktree": no_link_into_worktree,
        "maximum_path_length": plan.maximum_path_length,
        "selected_snapshot_capacity_bytes": plan.selected_snapshot_capacity_bytes,
        "vault_capacity_bytes": plan.vault_capacity_bytes,
        "private_replay_capacity_bytes": plan.private_replay_capacity_bytes,
        "compiler_temporary_capacity_bytes": plan.compiler_temporary_capacity_bytes,
        "public_production_temporary_capacity_bytes": (
            plan.public_production_temporary_capacity_bytes
        ),
        "safety_reserve_bytes": plan.safety_reserve_bytes,
        "selected_storage_plan_hash": plan.plan_hash,
        "status": (
            "PASS"
            if usage.free >= plan.required_free_bytes
            and vfs.f_favail >= M336J_MINIMUM_FREE_INODES
            and writable
            and atomic
            and synced
            else "FAIL"
        ),
    }
    return {**body, "receipt_hash": content_hash(body)}
