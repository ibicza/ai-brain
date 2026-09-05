"""Run the sole post-F20 acquisition, qualification, census, and selector."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import load_strict_json
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    run_fresh_acquisition_and_preflight,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _worktrees(repository: Path) -> tuple[Path, ...]:
    output = subprocess.run(
        ("git", "worktree", "list", "--porcelain"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(
        Path(line.removeprefix("worktree "))
        for line in output.splitlines()
        if line.startswith("worktree ")
    )


def _require_clean_exact_commit(repository: Path, expected: str) -> None:
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
    if head != expected or len(head) != 40 or status:
        raise ValueError("fresh acquisition requires a clean exact-F20 worktree")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--authority-statement", type=Path, required=True)
    parser.add_argument("--f20-sha", required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--selected-source-output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    _require_clean_exact_commit(repository, args.f20_sha)
    if args.public_output.exists():
        raise FileExistsError("fresh acquisition public output already exists")
    preflight = run_fresh_acquisition_and_preflight(
        pool=load_strict_json(args.pool.resolve(strict=True)),
        vault_root=args.vault,
        authority_statement=args.authority_statement.resolve(strict=True),
        f20_sha=args.f20_sha,
        timestamp=args.timestamp,
        host=args.host,
        ledger=RunProtocolLedger(args.ledger, git_worktrees=(repository,)),
        selected_source_output=args.selected_source_output,
        git_worktrees=_worktrees(repository),
    )
    args.public_output.mkdir(parents=True)
    outputs = {
        "acquisition_receipts.json": preflight.acquisition_report,
        "candidate_qualification.json": preflight.qualification_report,
        "portable_vault_manifest.json": asdict(preflight.portable_vault_manifest),
        "source_entry_binding_manifest.json": asdict(
            preflight.source_entry_binding_manifest
        ),
        "selectability_census.json": asdict(preflight.selectability_census),
        "selector_feasibility.json": asdict(preflight.feasibility_proof),
        "source_overlap_report.json": preflight.source_overlap_report,
        "disclosure_append.json": preflight.disclosure_append,
        "performance.json": preflight.performance_report,
        "protocol_ledger_receipt.json": asdict(
            RunProtocolLedger(args.ledger, git_worktrees=(repository,)).receipt()
        ),
    }
    if preflight.selected_manifest is not None:
        outputs["selected_source_manifest.json"] = asdict(preflight.selected_manifest)
    if preflight.selector_receipt is not None:
        outputs["selector_receipt.json"] = asdict(preflight.selector_receipt)
    for name, value in outputs.items():
        _write(args.public_output / name, value)
    summary_body = {
        "schema_version": 2,
        "f20_sha": args.f20_sha,
        "candidate_pool_hash": preflight.candidate_pool_hash,
        "candidate_count": preflight.acquisition_report["candidate_count"],
        "analysis_eligible_root_count": preflight.qualification_report[
            "analysis_eligible_root_count"
        ],
        "analysis_eligible_file_count": preflight.selectability_census.analysis_eligible_file_count,
        "production_supported_file_count": preflight.selectability_census.production_supported_file_count,
        "selectable_root_count": preflight.selectability_census.selectable_root_count,
        "selectable_file_count": preflight.selectability_census.selectable_file_count,
        "balanced_capacity": preflight.feasibility_proof.balanced_capacity,
        "feasibility_passed": preflight.feasibility_proof.hard_requirements_satisfied,
        "selector_invocation_count": (
            preflight.selector_receipt.selector_invocation_count
            if preflight.selector_receipt
            else 0
        ),
        "selector_rerun_count": (
            preflight.selector_receipt.selector_rerun_count
            if preflight.selector_receipt
            else 0
        ),
        "status": preflight.status,
        "preflight_report_hash": preflight.report_hash,
    }
    _write(
        args.public_output / "preflight_summary.json",
        {**summary_body, "report_hash": content_hash(summary_body)},
    )
    if preflight.status != "PASS":
        raise SystemExit("M-33.6e fresh preflight is BLOCKED; selector was not rerun")


if __name__ == "__main__":
    main()
