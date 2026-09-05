"""Complete the protocol only after both independent platform evaluations pass."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--windows-evaluation", type=Path, required=True)
    parser.add_argument("--karina-evaluation", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
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
        raise ValueError("evaluation completion requires a clean exact-H20 worktree")
    if args.output.exists():
        raise FileExistsError("fresh evaluation completion receipt already exists")
    windows = _load(args.windows_evaluation.resolve(strict=True))
    karina = _load(args.karina_evaluation.resolve(strict=True))
    comparison = _load(args.comparison.resolve(strict=True))
    metric_fields = (
        "production_reference_license_agreement",
        "false_automatic_license_identity_count",
        "selected_root_unresolved_disagreement_count",
        "location_precision",
        "location_recall",
        "semantic_precision",
        "semantic_recall",
        "trust_precision",
        "trust_coverage",
        "field_evidence_exactness",
        "resolution_agreement",
        "wrong_trusted_count",
        "post_trust_pack_failures",
        "candidate_pack_compiled",
        "candidate_replay_status",
        "runtime_status",
        "runtime_network_access_count",
        "status",
    )
    if (
        windows["platform"] != "windows"
        or karina["platform"] != "karina"
        or any(windows[name] != karina[name] for name in metric_fields)
        or windows["status"] != "PASS"
        or comparison["status"] != "PASS"
        or comparison["platform_independent_difference_count"] != 0
    ):
        raise ValueError("platform evaluations are not jointly complete")
    ledger = RunProtocolLedger(
        args.ledger.resolve(strict=True),
        git_worktrees=(repository,),
    )
    latest = ledger.events()[-1]
    if latest.event_type != "EVALUATION_RESERVED":
        raise ValueError("evaluation completion lacks its unique reservation")
    event = ledger.append(
        "EVALUATION_COMPLETED",
        f20_sha=latest.f20_sha,
        acquisition_run_id=latest.acquisition_run_id,
        candidate_pool_hash=latest.candidate_pool_hash,
        vault_tree_hash=latest.vault_tree_hash,
        qualification_manifest_hash=latest.qualification_manifest_hash,
        selectability_census_hash=latest.selectability_census_hash,
    )
    receipt = ledger.receipt()
    body = {
        "schema_version": 1,
        "windows_evaluation_hash": windows["report_hash"],
        "karina_evaluation_hash": karina["report_hash"],
        "platform_comparison_hash": comparison["report_hash"],
        "protocol_event_hash": event.event_hash,
        "protocol_ledger_receipt": asdict(receipt),
        "status": "PASS",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "receipt_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
