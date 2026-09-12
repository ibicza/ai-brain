from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_recovery import M336K5RecoveryLedger


def _append(ledger: M336K5RecoveryLedger, phase: str) -> None:
    ledger.append(
        branch="exp/stage3-m336k5-hermetic-python-final-v14",
        head_sha="a" * 40,
        phase=phase,
        worktree_status="DIRTY_IMPLEMENTATION",
        worktree_status_hash=content_hash(("status", phase)),
        completed_receipt_hashes=("b" * 64,),
        startup_policy_hash="c" * 64,
        resource_sample_count=2,
        resource_sample_chain_hash="d" * 64,
        official_ledger_states={"ACQUISITION": 0, "ROUTE": 0},
        official_vault_state="ABSENT",
        next_permitted_operation="CONTINUE_PREFREEZE_IMPLEMENTATION",
    )


def test_recovery_ledger_is_hash_chained_and_path_free(tmp_path: Path) -> None:
    path = tmp_path / "recovery.jsonl"
    ledger = M336K5RecoveryLedger(path)
    _append(ledger, "PHASE_09")
    _append(ledger, "PHASE_10")
    restored = M336K5RecoveryLedger(path)
    assert len(restored.checkpoints) == 2
    assert (
        restored.checkpoints[1].previous_checkpoint_hash
        == restored.checkpoints[0].checkpoint_hash
    )
    assert "\\" not in path.read_text(encoding="utf-8")


def test_recovery_ledger_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "recovery.jsonl"
    ledger = M336K5RecoveryLedger(path)
    _append(ledger, "PHASE_09")
    value = json.loads(path.read_text(encoding="utf-8"))
    value["phase"] = "TAMPERED"
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(M336K2ProtocolError):
        M336K5RecoveryLedger(path)


def test_recovery_checkpoint_rejects_private_path(tmp_path: Path) -> None:
    ledger = M336K5RecoveryLedger(tmp_path / "recovery.jsonl")
    with pytest.raises(M336K2ProtocolError):
        ledger.append(
            branch="exp/stage3-m336k5-hermetic-python-final-v14",
            head_sha="a" * 40,
            phase="C:/private/phase",
            worktree_status="CLEAN",
            worktree_status_hash="b" * 64,
            completed_receipt_hashes=(),
            startup_policy_hash="c" * 64,
            resource_sample_count=0,
            resource_sample_chain_hash="0" * 64,
            official_ledger_states={},
            official_vault_state="ABSENT",
            next_permitted_operation="NEXT",
        )
