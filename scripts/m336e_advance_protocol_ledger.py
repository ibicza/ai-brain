"""Append the one exact next event to an existing M-33.6e ledger."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != args.expected_head or len(head) != 40 or status:
        raise ValueError("ledger advance requires a clean exact worktree")
    ledger = RunProtocolLedger(args.ledger, git_worktrees=(repository,))
    events = ledger.events()
    if not events:
        raise ValueError("protocol ledger is empty")
    latest = events[-1]
    ledger.append(
        args.event,
        f20_sha=latest.f20_sha,
        acquisition_run_id=latest.acquisition_run_id,
        candidate_pool_hash=latest.candidate_pool_hash,
        vault_tree_hash=latest.vault_tree_hash,
        qualification_manifest_hash=latest.qualification_manifest_hash,
        selectability_census_hash=latest.selectability_census_hash,
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        canonical_json(asdict(ledger.receipt())) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
