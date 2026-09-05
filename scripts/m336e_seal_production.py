"""Verify one oracle-free production and append its exact protocol seal event."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger


def _load(root: Path, name: str):
    return json.loads((root / name).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
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
        raise ValueError("production sealing requires a clean exact-F20 worktree")
    if args.output.exists():
        raise FileExistsError("fresh production seal already exists")
    root = args.production_root.resolve(strict=True)
    summary = _load(root, "production_summary.json")
    counts = _load(root, "production_counts.json")
    process = _load(root, "production_process_audit.json")
    files = _load(root, "production_file_access_audit.json")
    state = _load(root, "production_state_audit.json")
    process_counts = tuple(
        value
        for name, value in process.items()
        if name.endswith(("count", "attempts")) and isinstance(value, int)
    )
    state_counts = tuple(
        value
        for name, value in state.items()
        if name.endswith(("count", "attempts")) and isinstance(value, int)
    )
    if (
        summary["platform"] != args.platform
        or summary["status"] != "PASS"
        or summary["candidate_replay_status"] != "PASS"
        or summary["production_evaluator_dependency_count"] != 0
        or summary["production_golden_read_count"] != 0
        or summary["torch_imported"] is not False
        or counts["post_trust_pack_failures"] != 0
        or any(process_counts)
        or any(state_counts)
        or files["forbidden_read_count"] != 0
    ):
        raise ValueError("oracle-free production is not sealable")
    ledger = RunProtocolLedger(
        args.ledger.resolve(strict=True),
        git_worktrees=(repository,),
    )
    latest = ledger.events()[-1]
    event_type = (
        "WINDOWS_PRODUCTION_SEALED"
        if args.platform == "windows"
        else "KARINA_PRODUCTION_SEALED"
    )
    event = ledger.append(
        event_type,
        f20_sha=latest.f20_sha,
        acquisition_run_id=latest.acquisition_run_id,
        candidate_pool_hash=latest.candidate_pool_hash,
        vault_tree_hash=latest.vault_tree_hash,
        qualification_manifest_hash=latest.qualification_manifest_hash,
        selectability_census_hash=latest.selectability_census_hash,
    )
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "production_output_hash": summary["production_output_hash"],
        "production_batch_hash": summary["production_batch_hash"],
        "candidate_pack_hash": summary["candidate_pack_hash"],
        "candidate_tree_hash": summary["candidate_tree_hash"],
        "candidate_replay_hash": summary["candidate_replay_hash"],
        "protocol_event_hash": event.event_hash,
        "protocol_ledger_receipt_hash": ledger.receipt().receipt_hash,
        "production_evaluator_read_count": 0,
        "production_golden_read_count": 0,
        "production_network_access_count": 0,
        "post_trust_pack_failure_count": 0,
        "status": "PASS",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "seal_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    # Force one final canonical ledger verification after emitting the seal.
    asdict(ledger.receipt())


if __name__ == "__main__":
    main()
