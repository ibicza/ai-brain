"""Append one path-free M336K5 recovery checkpoint from a private request."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_recovery import M336K5RecoveryLedger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request)
    expected = {
        "ledger",
        "branch",
        "head_sha",
        "phase",
        "worktree_status",
        "worktree_status_hash",
        "completed_receipt_hashes",
        "startup_policy_hash",
        "resource_sample_count",
        "resource_sample_chain_hash",
        "official_ledger_states",
        "official_vault_state",
        "next_permitted_operation",
        "output",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K5 recovery request fields changed")
    output = Path(request.pop("output")).resolve(strict=False)
    ledger = M336K5RecoveryLedger(Path(request.pop("ledger")))
    checkpoint = ledger.append(**request)
    write_canonical_json(output, asdict(checkpoint))


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("M336K5 recovery request is not an object")
    return value


if __name__ == "__main__":
    main()
