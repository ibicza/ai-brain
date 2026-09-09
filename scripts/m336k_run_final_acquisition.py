"""Execute the frozen M-33.6k candidate-isolated final acquisition once."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    append_disclosed_java_entries_v2,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336k_acquisition import M336KAcquisitionLedger
from ai_brain.stage3.acquisition.m336k_final_pipeline import (
    m336k_final_acquisition_authorization_from_dict,
    run_m336k_frozen_final_acquisition,
)
from ai_brain.stage3.acquisition.m336k_publication import (
    build_m336k_compatibility_qualification,
    build_m336k_compatibility_summary,
    build_m336k_disclosure_entries,
)


def _load(path: Path) -> dict:
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--f27-sha", required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--acquisition-policy", type=Path, required=True)
    parser.add_argument("--authority-statement", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--private-registry-output", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--private-preflight", type=Path, required=True)
    parser.add_argument("--unused-selected-source", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    public = args.public_output.resolve(strict=False)
    if public.exists():
        raise FileExistsError("M336K final public output must be fresh")
    if public.is_relative_to(repository):
        raise ValueError("M336K final public output must remain outside Git")
    authorization = m336k_final_acquisition_authorization_from_dict(
        _load(args.authorization)
    )
    registry = args.registry.resolve(strict=True)
    private_registry = args.private_registry_output.resolve(strict=False)
    if private_registry.exists():
        raise FileExistsError("M336K final disclosure registry copy must be fresh")
    if private_registry.is_relative_to(repository):
        raise ValueError("M336K final disclosure registry must remain outside Git")
    ledger = M336KAcquisitionLedger(
        args.ledger.resolve(strict=False), git_worktrees=(repository,)
    )
    try:
        result = run_m336k_frozen_final_acquisition(
            repository=repository,
            expected_f27_sha=args.f27_sha,
            pool=_load(args.pool),
            authorization=authorization,
            acquisition_policy=_load(args.acquisition_policy),
            authority_statement=args.authority_statement.resolve(strict=True),
            vault_root=args.vault.resolve(strict=False),
            ledger=ledger,
            private_preflight_path=args.private_preflight.resolve(strict=False),
            unused_selected_source_output=args.unused_selected_source.resolve(
                strict=False
            ),
            host="WINDOWS",
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        public.mkdir(parents=True)
        ledger_receipt = ledger.receipt()
        body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K_FINAL_OUTCOME_C_RECEIPT",
            "exact_f27_sha": args.f27_sha,
            "authorization_hash": authorization.authorization_hash,
            "acquisition_run_id": authorization.acquisition_run_id,
            "final_ledger_event": ledger_receipt.final_event,
            "acquisition_reservation_count": (
                ledger_receipt.acquisition_reservation_count
            ),
            "acquisition_start_count": ledger_receipt.acquisition_start_count,
            "all_candidates_terminal_count": (
                ledger_receipt.all_candidates_terminal_count
            ),
            "acquisition_completion_count": (
                ledger_receipt.acquisition_completion_count
            ),
            "acquisition_failure_count": ledger_receipt.acquisition_failure_count,
            "acquisition_rerun_count": ledger_receipt.acquisition_rerun_count,
            "failure_class": type(error).__name__,
            "failure_reason_hash": content_hash(str(error)),
            "ledger_receipt_hash": ledger_receipt.receipt_hash,
            "status": "OUTCOME C — BLOCKED",
        }
        _write(
            public / "final_outcome_c_receipt.json",
            {**body, "receipt_hash": content_hash(body)},
        )
        raise

    public.mkdir(parents=True)
    terminal_rows = tuple(
        asdict(item.terminal_receipt) for item in result.candidate_outcomes
    )
    archive_rows = tuple(
        {
            "candidate_family_id": item.terminal_receipt.candidate_family_id,
            "archive_decision": item.archive_result.receipt.decision
            if item.archive_result
            else None,
            "archive_inspection_receipt_hash": (
                item.archive_result.receipt.receipt_hash
                if item.archive_result
                else None
            ),
            "archive_binding_hash": item.archive_binding.binding_hash
            if item.archive_binding
            else None,
        }
        for item in result.candidate_outcomes
    )
    status_counts = Counter(item["terminal_status"] for item in terminal_rows)
    terminal_body = {
        "schema_version": 1,
        "candidate_count": len(terminal_rows),
        "terminal_count": len(terminal_rows),
        "missing_terminal_count": result.global_receipt.missing_terminal_count,
        "duplicate_terminal_count": result.global_receipt.duplicate_terminal_count,
        "terminal_status_counts": tuple(sorted(status_counts.items())),
        "rows": terminal_rows,
    }
    archive_body = {
        "schema_version": 1,
        "candidate_count": len(archive_rows),
        "authoritative_archive_inspection_count": (
            result.global_receipt.authoritative_archive_inspection_count
        ),
        "rows": archive_rows,
    }
    qualification = build_m336k_compatibility_qualification(
        result.preflight, result.candidate_outcomes
    )
    qualification_summary = build_m336k_compatibility_summary(
        exact_sha=args.f27_sha,
        preflight=result.preflight,
        qualification=qualification,
        registry_root=registry,
    )
    entries = build_m336k_disclosure_entries(
        result.candidate_outcomes,
        disclosure_reason="FINAL_ACQUISITION_F27",
        originating_chain=(
            f"{authorization.exact_r27_sha}/{authorization.exact_q27_sha}/"
            f"{args.f27_sha}"
        ),
    )
    shutil.copytree(registry, private_registry)
    if entries:
        manifest, append_receipt = append_disclosed_java_entries_v2(
            private_registry,
            entries,
            acquisition_run_id=authorization.acquisition_run_id,
            f20_sha=args.f27_sha,
        )
        append_receipt_value = asdict(append_receipt)
        resulting_manifest_hash = manifest.manifest_hash
        resulting_entry_count = len(manifest.entry_hashes)
    else:
        verify_disclosed_java_registry(private_registry)
        current = _load(private_registry / "registry_manifest.json")
        append_receipt_value = None
        resulting_manifest_hash = current["manifest_hash"]
        resulting_entry_count = len(current["entry_hashes"])
    disclosure_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_FINAL_DISCLOSURE_APPEND",
        "exact_f27_sha": args.f27_sha,
        "attempted_candidate_count": len(result.candidate_outcomes),
        "downloaded_source_body_count": len(entries),
        "appended_entry_count": len(entries),
        "resulting_registry_entry_count": resulting_entry_count,
        "resulting_registry_manifest_hash": resulting_manifest_hash,
        "registry_append_receipt_hash": (
            append_receipt_value["receipt_hash"] if append_receipt_value else None
        ),
        "status": "PASS",
    }
    _write(public / "final_acquisition_receipt.json", result.public_receipt)
    _write(
        public / "final_candidate_terminal_matrix.json",
        {**terminal_body, "report_hash": content_hash(terminal_body)},
    )
    _write(
        public / "final_archive_decision_summary.json",
        {**archive_body, "report_hash": content_hash(archive_body)},
    )
    _write(
        public / "final_global_acquisition_receipt.json",
        asdict(result.global_receipt),
    )
    _write(
        public / "final_acquisition_ledger_receipt.json",
        asdict(result.ledger_receipt),
    )
    _write(public / "candidate_qualification.json", qualification)
    _write(public / "preflight_summary.json", qualification_summary)
    _write(
        public / "source_entry_binding_manifest.json",
        asdict(result.preflight.source_entry_binding_manifest),
    )
    _write(
        public / "selectability_census.json",
        asdict(result.preflight.selectability_census),
    )
    _write(
        public / "selector_feasibility.json",
        asdict(result.preflight.feasibility_proof),
    )
    if append_receipt_value:
        _write(
            public / "final_disclosure_registry_append_receipt.json",
            append_receipt_value,
        )
    _write(
        public / "final_disclosure_append_summary.json",
        {**disclosure_body, "report_hash": content_hash(disclosure_body)},
    )
    leak = scan_fresh_source_leaks(args.vault.resolve(strict=True), public)
    _write(public / "source_leak_report.json", leak)
    if result.preflight.status != "PASS" or leak["status"] != "PASS":
        blocked_body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K_FINAL_OUTCOME_C_RECEIPT",
            "exact_f27_sha": args.f27_sha,
            "authorization_hash": authorization.authorization_hash,
            "acquisition_run_id": authorization.acquisition_run_id,
            "final_ledger_event": result.ledger_receipt.final_event,
            "acquisition_reservation_count": (
                result.ledger_receipt.acquisition_reservation_count
            ),
            "acquisition_start_count": result.ledger_receipt.acquisition_start_count,
            "all_candidates_terminal_count": (
                result.ledger_receipt.all_candidates_terminal_count
            ),
            "acquisition_completion_count": (
                result.ledger_receipt.acquisition_completion_count
            ),
            "acquisition_failure_count": (
                result.ledger_receipt.acquisition_failure_count
            ),
            "acquisition_rerun_count": result.ledger_receipt.acquisition_rerun_count,
            "pool_qualification_status": result.preflight.status,
            "source_leak_count": leak["fresh_source_leak_count"],
            "status": "OUTCOME C — BLOCKED",
        }
        _write(
            public / "final_outcome_c_receipt.json",
            {**blocked_body, "receipt_hash": content_hash(blocked_body)},
        )
        raise RuntimeError("M336K final pool-level qualification blocked")


if __name__ == "__main__":
    main()
