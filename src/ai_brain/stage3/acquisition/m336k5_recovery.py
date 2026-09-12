"""Path-free hash-chained recovery checkpoints for M-33.6k.5."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Self

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REF = re.compile(r"(?:[0-9a-f]{40}|NOT_CREATED|ABSENT|PRESENT)\Z")
_BRANCH = "exp/stage3-m336k5-hermetic-python-final-v14"


@dataclass(frozen=True)
class M336K5RecoveryCheckpoint:
    schema_version: int
    contract_role: str
    sequence: int
    previous_checkpoint_hash: str
    branch: str
    head_sha: str
    phase: str
    worktree_status: str
    worktree_status_hash: str
    completed_receipt_hashes: tuple[str, ...]
    startup_policy_hash: str
    resource_sample_count: int
    resource_sample_chain_hash: str
    official_ledger_states: tuple[tuple[str, int], ...]
    official_vault_state: str
    next_permitted_operation: str
    checkpoint_hash: str

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K5 recovery checkpoint fields changed")
        result = cls(
            **{
                **value,
                "completed_receipt_hashes": tuple(value["completed_receipt_hashes"]),
                "official_ledger_states": tuple(
                    (str(name), int(count))
                    for name, count in value["official_ledger_states"]
                ),
            }
        )
        verify_m336k5_recovery_checkpoint(result)
        return result


def _canonical_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _body(checkpoint: M336K5RecoveryCheckpoint) -> dict:
    value = asdict(checkpoint)
    value.pop("checkpoint_hash")
    return value


def _is_private_text(value: str) -> bool:
    return (
        "\\" in value
        or "/" in value
        or re.match(r"[A-Za-z]:", value) is not None
        or value.startswith("~")
    )


def verify_m336k5_recovery_checkpoint(
    checkpoint: M336K5RecoveryCheckpoint,
) -> None:
    hashes = (
        checkpoint.previous_checkpoint_hash,
        checkpoint.worktree_status_hash,
        *checkpoint.completed_receipt_hashes,
        checkpoint.startup_policy_hash,
        checkpoint.resource_sample_chain_hash,
        checkpoint.checkpoint_hash,
    )
    labels = (
        checkpoint.phase,
        checkpoint.worktree_status,
        checkpoint.official_vault_state,
        checkpoint.next_permitted_operation,
        *(name for name, _count in checkpoint.official_ledger_states),
    )
    if (
        checkpoint.schema_version != 1
        or checkpoint.contract_role != "M336K5_RECOVERY_CHECKPOINT"
        or checkpoint.sequence < 1
        or any(_HASH.fullmatch(value) is None for value in hashes)
        or _REF.fullmatch(checkpoint.head_sha) is None
        or checkpoint.branch != _BRANCH
        or any(_is_private_text(value) for value in labels)
        or tuple(sorted(checkpoint.completed_receipt_hashes))
        != checkpoint.completed_receipt_hashes
        or len(set(checkpoint.completed_receipt_hashes))
        != len(checkpoint.completed_receipt_hashes)
        or tuple(sorted(checkpoint.official_ledger_states))
        != checkpoint.official_ledger_states
        or any(count < 0 for _name, count in checkpoint.official_ledger_states)
        or checkpoint.official_vault_state not in {"ABSENT", "PRESENT"}
        or content_hash(_body(checkpoint)) != checkpoint.checkpoint_hash
    ):
        raise M336K2ProtocolError("M336K5 recovery checkpoint is invalid")


class M336K5RecoveryLedger:
    """Append-only external checkpoint ledger with a verified hash chain."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve(strict=False)
        self._checkpoints = self._load()

    @property
    def checkpoints(self) -> tuple[M336K5RecoveryCheckpoint, ...]:
        return self._checkpoints

    def _load(self) -> tuple[M336K5RecoveryCheckpoint, ...]:
        if not self.path.exists():
            return ()
        result: list[M336K5RecoveryCheckpoint] = []
        with self.path.open("r", encoding="utf-8", newline="") as stream:
            for raw in stream:
                if not raw.endswith("\n") or raw.endswith("\r\n"):
                    raise M336K2ProtocolError("M336K5 recovery ledger newline changed")
                value = json.loads(raw)
                result.append(M336K5RecoveryCheckpoint.from_dict(value))
        previous = "0" * 64
        for sequence, checkpoint in enumerate(result, start=1):
            if (
                checkpoint.sequence != sequence
                or checkpoint.previous_checkpoint_hash != previous
            ):
                raise M336K2ProtocolError("M336K5 recovery checkpoint chain changed")
            previous = checkpoint.checkpoint_hash
        return tuple(result)

    def append(
        self,
        *,
        branch: str,
        head_sha: str,
        phase: str,
        worktree_status: str,
        worktree_status_hash: str,
        completed_receipt_hashes: Iterable[str],
        startup_policy_hash: str,
        resource_sample_count: int,
        resource_sample_chain_hash: str,
        official_ledger_states: Mapping[str, int],
        official_vault_state: str,
        next_permitted_operation: str,
    ) -> M336K5RecoveryCheckpoint:
        previous = (
            self._checkpoints[-1].checkpoint_hash if self._checkpoints else "0" * 64
        )
        body = {
            "schema_version": 1,
            "contract_role": "M336K5_RECOVERY_CHECKPOINT",
            "sequence": len(self._checkpoints) + 1,
            "previous_checkpoint_hash": previous,
            "branch": branch,
            "head_sha": head_sha,
            "phase": phase,
            "worktree_status": worktree_status,
            "worktree_status_hash": worktree_status_hash,
            "completed_receipt_hashes": tuple(sorted(set(completed_receipt_hashes))),
            "startup_policy_hash": startup_policy_hash,
            "resource_sample_count": resource_sample_count,
            "resource_sample_chain_hash": resource_sample_chain_hash,
            "official_ledger_states": tuple(sorted(official_ledger_states.items())),
            "official_vault_state": official_vault_state,
            "next_permitted_operation": next_permitted_operation,
        }
        checkpoint = M336K5RecoveryCheckpoint(
            **body, checkpoint_hash=content_hash(body)
        )
        verify_m336k5_recovery_checkpoint(checkpoint)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(_canonical_line(asdict(checkpoint)) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._checkpoints = (*self._checkpoints, checkpoint)
        return checkpoint
