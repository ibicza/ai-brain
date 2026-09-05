"""Run M-33.6e disclosed qualification, census, proof, and rehearsal selector."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import (
    M336E_DISCLOSED_RUN_ID,
    M336E_DISCLOSED_SELECTOR_SEED,
    load_strict_json,
    materialize_selected_source_snapshot,
    run_disclosed_full_path_preflight,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336e_selectability import select_final_sources_once


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--historical-vault-manifest", type=Path, required=True)
    parser.add_argument("--historical-qualification", type=Path, required=True)
    parser.add_argument("--historical-f19-sha", required=True)
    parser.add_argument("--freeze-sha", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--selected-source-output", type=Path, required=True)
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
        raise ValueError("disclosed preflight requires a clean exact worktree")
    if args.public_output.exists() or args.selected_source_output.exists():
        raise FileExistsError("disclosed rehearsal outputs must be new")
    pool = load_strict_json(args.pool.resolve(strict=True))
    preflight = run_disclosed_full_path_preflight(
        pool=pool,
        vault_root=args.vault.resolve(strict=True),
        authority_statement=args.authority.resolve(strict=True),
        historical_f19_sha=args.historical_f19_sha,
        historical_public_vault_manifest=load_strict_json(
            args.historical_vault_manifest.resolve(strict=True)
        ),
        expected_historical_qualification=load_strict_json(
            args.historical_qualification.resolve(strict=True)
        ),
    )
    if preflight.status != "PASS":
        raise ValueError("disclosed selectability preflight failed")
    context = {
        "f20_sha": args.freeze_sha,
        "acquisition_run_id": M336E_DISCLOSED_RUN_ID,
        "candidate_pool_hash": preflight.candidate_pool_hash,
    }
    sealed_context = {
        **context,
        "vault_tree_hash": preflight.vault_manifest.portable_tree_hash,
    }
    qualified_context = {
        **sealed_context,
        "qualification_manifest_hash": preflight.historical_qualification_report[
            "report_hash"
        ],
    }
    census_context = {
        **qualified_context,
        "selectability_census_hash": preflight.selectability_census.census_hash,
    }
    ledger = RunProtocolLedger(args.ledger, git_worktrees=(repository,))
    ledger.append("FREEZE_VERIFIED", **context)
    ledger.append("ACQUISITION_RESERVED", **context)
    ledger.append("ACQUISITION_COMPLETED", **context)
    ledger.append("VAULT_SEALED", **sealed_context)
    ledger.append("QUALIFICATION_COMPLETED", **qualified_context)
    ledger.append("SELECTABILITY_CENSUS_COMPLETED", **census_context)
    selected, selector = select_final_sources_once(
        preflight.selectability_census,
        preflight.feasibility_proof,
        preflight.source_entry_binding_manifest,
        ledger,
        selector_seed=M336E_DISCLOSED_SELECTOR_SEED,
        **census_context,
    )
    materialize_selected_source_snapshot(
        vault_root=args.vault.resolve(strict=True),
        binding_manifest=preflight.source_entry_binding_manifest,
        selected_manifest=selected,
        destination=args.selected_source_output,
    )

    args.public_output.mkdir(parents=True)
    _write(
        args.public_output / "portable_vault_manifest.json",
        asdict(preflight.vault_manifest),
    )
    _write(
        args.public_output / "candidate_qualification.json",
        {
            "schema_version": 1,
            "candidate_count": len(preflight.candidates),
            "candidates": preflight.candidates,
            "historical_qualification_report_hash": preflight.historical_qualification_report[
                "report_hash"
            ],
            "report_hash": content_hash(preflight.candidates),
        },
    )
    _write(
        args.public_output / "source_entry_binding_manifest.json",
        asdict(preflight.source_entry_binding_manifest),
    )
    _write(
        args.public_output / "selectability_census.json",
        asdict(preflight.selectability_census),
    )
    _write(
        args.public_output / "selector_feasibility.json",
        asdict(preflight.feasibility_proof),
    )
    _write(args.public_output / "selected_source_manifest.json", asdict(selected))
    _write(args.public_output / "selector_receipt.json", asdict(selector))
    _write(
        args.public_output / "protocol_ledger_receipt.json", asdict(ledger.receipt())
    )
    summary_body = {
        "schema_version": 1,
        "status": "PASS",
        "preflight_report_hash": preflight.report_hash,
        "candidate_count": len(preflight.candidates),
        "analysis_eligible_root_count": preflight.historical_qualification_report[
            "analysis_eligible_root_count"
        ],
        "analysis_eligible_file_count": preflight.selectability_census.analysis_eligible_file_count,
        "parser_valid_file_count": preflight.selectability_census.parser_valid_file_count,
        "callable_file_count": preflight.selectability_census.callable_file_count,
        "production_supported_file_count": preflight.selectability_census.production_supported_file_count,
        "selectable_root_count": preflight.selectability_census.selectable_root_count,
        "selectable_file_count": preflight.selectability_census.selectable_file_count,
        "balanced_capacity": preflight.feasibility_proof.balanced_capacity,
        "selected_file_count": selected.file_count,
        "selected_root_count": selected.root_count,
        "maximum_one_root_count": max(
            count for _root, count in selected.root_distribution
        ),
        "selector_invocation_count": selector.selector_invocation_count,
        "selector_rerun_count": selector.selector_rerun_count,
        "root_distribution": selected.root_distribution,
        "portable_vault_file_count": preflight.vault_manifest.file_count,
        "portable_vault_tree_hash": preflight.vault_manifest.portable_tree_hash,
        "historical_qualification_equal": preflight.historical_qualification_equal,
        "authority_receipt_failure_count": preflight.authority_receipt_failure_count,
    }
    _write(
        args.public_output / "preflight_summary.json",
        {**summary_body, "report_hash": content_hash(summary_body)},
    )


if __name__ == "__main__":
    main()
