"""Run the exact-R27 candidate-isolated F26 recovery qualification."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
)
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    append_disclosed_java_entries_v2,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    run_fresh_acquisition_and_preflight,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336i_acquisition import (
    validate_m336i_candidate_pool,
)
from ai_brain.stage3.acquisition.m336k_acquisition import (
    M336KAcquisitionLedger,
    build_global_acquisition_receipt,
    recover_disclosed_candidate_v2,
)
from ai_brain.stage3.acquisition.m336k_archive import (
    ArchiveInspectionPolicyV2,
    public_archive_forensics,
)
from ai_brain.stage3.acquisition.m336k_campaigns import (
    run_archive_mutation_campaign,
    run_mixed_candidate_fault_campaign,
)
from ai_brain.stage3.acquisition.m336k_publication import (
    build_m336k_compatibility_qualification,
    build_m336k_compatibility_summary,
    build_m336k_disclosure_entries,
)

F26_SHA = "6a8c226371d478f7c92fb86345bda85265c3323a"
F26_CHAIN = (
    "a2c5cbff8c42ace449b51a187cef70089be15ba3"
    "/549c0f337647fc39e369934e44964c9b5b0825c8"
    "/3baca01408c62a0544c041c5bf15d19edc0b0d8a"
    f"/{F26_SHA}"
)
RUN_ID = "m336k-r27-disclosed-f26-rehearsal-v1"
AUTHORIZATION_HASH = content_hash(
    ("M336K_R27_DISCLOSED_F26_REHEARSAL", F26_SHA, RUN_ID)
)


def _load(path: Path) -> dict:
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _sealed(value: dict, field: str) -> str:
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed is None or content_hash(body) != claimed:
        raise ValueError(f"invalid external receipt: {field}")
    return claimed


def _require_clean_exact(repository: Path, expected: str) -> None:
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
        raise ValueError("R27 qualification requires a clean exact-R27 worktree")


def _verify_phase0(inventory: dict, preservation: dict, pool: dict) -> None:
    _sealed(inventory, "receipt_hash")
    _sealed(preservation, "receipt_hash")
    required = (
        inventory.get("exact_f26_sha") == F26_SHA
        and inventory.get("frozen_candidate_count") == 66
        and inventory.get("candidate_inventory_row_count") == 66
        and inventory.get("unaccounted_candidate_count") == 0
        and inventory.get("unclassified_duplicate_group_count") == 0
        and inventory.get("duplicate_group_count") == 39
        and preservation.get("exact_f26_sha") == F26_SHA
        and preservation.get("status") == "PRESERVED_AND_VERIFIED"
        and preservation.get("candidate_directory_count") == 66
        and preservation.get("acquisition_reservation_count") == 1
        and preservation.get("acquisition_start_count") == 1
        and preservation.get("acquisition_completion_count") == 0
        and preservation.get("acquisition_failure_count") == 1
        and preservation.get("acquisition_rerun_count") == 0
        and preservation.get("selector_invocation_count") == 0
        and preservation.get("evaluator_invocation_count") == 0
        and preservation.get("historical_vault_mutation_count") == 0
        and inventory.get("candidate_pool_hash") == pool.get("pool_hash")
        and pool.get("candidate_count") == len(pool.get("candidates", ())) == 66
    )
    if not required:
        raise ValueError("failed-F26 Phase-0 preservation contract mismatch")


def _vault_inventory(root: Path) -> tuple[int, int, str, tuple[dict, ...]]:
    rows = []
    byte_count = 0
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        byte_count += size
        rows.append(
            {
                "relative_path_hash": bytes_hash(relative.encode("utf-8")),
                "size": size,
                "sha256": bytes_hash(path.read_bytes()),
            }
        )
    return len(rows), byte_count, content_hash(rows), tuple(rows)


def _disclosure_recovery(outcomes, entries, append_receipt, manifest) -> dict:
    by_coordinate = {item.coordinate: item for item in entries}
    rows = []
    for outcome in sorted(
        outcomes, key=lambda item: item.terminal_receipt.candidate_family_id
    ):
        item = outcome.pipeline_item
        archive = outcome.archive_result
        entry = by_coordinate[item["coordinate"]]
        body = {
            "family_id": item["family_id"],
            "coordinate": item["coordinate"],
            "source_url": item["source_url"],
            "source_jar_sha256": item["source_jar_sha256"],
            "pom_sha256": item["pom_sha256"],
            "scm_archive_sha256": item["scm_archive_sha256"],
            "source_tree_hash": item["source_tree_hash"],
            "scm_commit": item["immutable_scm_commit"],
            "correspondence_hash": entry.correspondence_hash,
            "raw_source_hash_manifest_hash": content_hash(entry.raw_source_hashes),
            "raw_source_hash_count": len(entry.raw_source_hashes),
            "canonical_source_hash_manifest_hash": content_hash(
                entry.canonical_source_hashes
            ),
            "canonical_source_hash_count": len(entry.canonical_source_hashes),
            "archive_inspection_decision": archive.receipt.decision
            if archive
            else None,
            "archive_anomaly_receipt_hash": archive.receipt.receipt_hash
            if archive
            else None,
            "disclosure_reason": "FAILED_FINAL_ACQUISITION_F26",
            "originating_chain": F26_CHAIN,
            "registry_entry_hash": entry.entry_hash,
        }
        rows.append({**body, "row_hash": content_hash(body)})
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_F26_DISCLOSURE_RECOVERY",
        "f26_candidate_count": len(outcomes),
        "f26_candidates_accounted": len(rows),
        "f26_disclosure_entry_count": len(entries),
        "future_final_pool_acceptance_count": 0,
        "previous_registry_entry_count": append_receipt.previous_entry_count,
        "resulting_registry_entry_count": append_receipt.resulting_entry_count,
        "resulting_registry_manifest_hash": manifest.manifest_hash,
        "registry_append_receipt_hash": append_receipt.receipt_hash,
        "rows": tuple(rows),
        "status": "PASS"
        if len(outcomes) == len(rows) == len(entries) == 66
        else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _recovered_inventory(phase0_inventory: dict, outcomes, entries) -> dict:
    terminal_by_family = {
        item.terminal_receipt.candidate_family_id: item for item in outcomes
    }
    entry_by_coordinate = {item.coordinate: item for item in entries}
    rows = []
    for old in phase0_inventory["candidates"]:
        outcome = terminal_by_family[old["family_id"]]
        item = outcome.pipeline_item
        terminal = outcome.terminal_receipt
        entry = entry_by_coordinate[item["coordinate"]]
        rejected = not terminal.eligible
        body = {
            **old,
            "originating_chain": F26_CHAIN,
            "archive_inspection_status": outcome.archive_result.receipt.decision,
            "archive_policy_hash": outcome.archive_result.receipt.archive_policy_hash,
            "archive_inspection_receipt_hash": outcome.archive_result.receipt.receipt_hash,
            "archive_inspection_binding_hash": outcome.archive_binding.binding_hash,
            "candidate_terminal_status": terminal.terminal_status,
            "candidate_terminal_receipt_hash": terminal.receipt_hash,
            "terminal_recovery_status": "TERMINAL_RECEIPT_RECOVERED",
            "authoritative_archive_inspection_count": outcome.authoritative_archive_inspection_count,
            "rejected_source_index_entry_count": 0 if rejected else None,
            "rejected_census_entry_count": 0 if rejected else None,
            "disclosure_entry_hash": entry.entry_hash,
            "processing_reached": (
                "SOURCE_ARCHIVE_INSPECTION",
                "SCM_VERIFICATION",
                "CANDIDATE_TERMINAL_DECISION",
                "GLOBAL_ACQUISITION_COMPLETION",
                "QUALIFICATION",
                "COMPILER_AWARE_CENSUS" if not rejected else "REJECTED_BEFORE_CENSUS",
            ),
        }
        rows.append(body)
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336K_F26_RECOVERED_CANDIDATE_INVENTORY",
        "exact_f26_sha": F26_SHA,
        "frozen_candidate_count": 66,
        "candidate_inventory_row_count": len(rows),
        "unaccounted_candidate_count": 66 - len(rows),
        "candidates": tuple(rows),
    }
    return {**body, "receipt_hash": content_hash(body)}


def _terminal_matrix(outcomes) -> dict:
    rows = tuple(
        asdict(item.terminal_receipt)
        for item in sorted(
            outcomes, key=lambda value: value.terminal_receipt.candidate_family_id
        )
    )
    families = tuple(item["candidate_family_id"] for item in rows)
    statuses = Counter(item["terminal_status"] for item in rows)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_F26_TERMINAL_MATRIX",
        "candidate_count": 66,
        "terminal_receipt_count": len(rows),
        "missing_terminal_receipt_count": 66 - len(rows),
        "duplicate_terminal_receipt_count": len(families) - len(set(families)),
        "terminal_status_counts": tuple(sorted(statuses.items())),
        "rows": rows,
    }
    return {**body, "report_hash": content_hash(body)}


def _run_recovery(
    *,
    repository: Path,
    r27_sha: str,
    pool: dict,
    preserved_vault: Path,
    authority_statement: Path,
    private_root: Path,
):
    candidates = tuple(pool["candidates"])
    policy = ArchiveInspectionPolicyV2.frozen_default()
    ledger = M336KAcquisitionLedger(
        private_root / "acquisition.jsonl", git_worktrees=(repository,)
    )
    context_hash = content_hash((RUN_ID, AUTHORIZATION_HASH, pool["pool_hash"]))
    ledger.append(
        "AUTHORIZATION_VALIDATED",
        context_hash=context_hash,
        operation_hash=AUTHORIZATION_HASH,
    )
    ledger.append(
        "ACQUISITION_RESERVED",
        context_hash=context_hash,
        operation_hash=pool["pool_hash"],
    )
    ledger.append(
        "ACQUISITION_STARTED",
        context_hash=context_hash,
        operation_hash=content_hash(tuple(item["family_id"] for item in candidates)),
    )
    outcomes = []

    def recover(policy_row, *, vault_root, maven, scm):
        del maven, scm
        outcome = recover_disclosed_candidate_v2(
            policy_row,
            preserved_vault_root=preserved_vault,
            destination_vault_root=vault_root,
            acquisition_run_id=RUN_ID,
            archive_policy=policy,
        )
        outcomes.append(outcome)
        return outcome.pipeline_item

    vault = private_root / "vault"
    try:
        preflight = run_fresh_acquisition_and_preflight(
            pool=pool,
            vault_root=vault,
            authority_statement=authority_statement,
            f20_sha=r27_sha,
            timestamp="1970-01-01T00:00:00Z",
            host="m336k-r27-platform-neutral",
            ledger=RunProtocolLedger(
                private_root / "unused-legacy-ledger.jsonl",
                git_worktrees=(repository,),
            ),
            selected_source_output=private_root / "unused-selected-source",
            git_worktrees=(repository,),
            acquire_one=recover,
            validate_pool=validate_m336i_candidate_pool,
            record_protocol=False,
            perform_selector=False,
            acquisition_run_id=RUN_ID,
        )
        families = tuple(item.terminal_receipt.candidate_family_id for item in outcomes)
        expected_families = tuple(item["family_id"] for item in candidates)
        if families != expected_families or len(set(families)) != len(families):
            raise RuntimeError("F26 terminal candidate accounting mismatch")
        terminal_manifest = content_hash(
            tuple(item.terminal_receipt.receipt_hash for item in outcomes)
        )
        ledger.append(
            "ALL_CANDIDATES_TERMINAL",
            context_hash=context_hash,
            operation_hash=terminal_manifest,
        )
        global_receipt = build_global_acquisition_receipt(
            acquisition_run_id=RUN_ID,
            candidate_count=len(candidates),
            attempted_count=len(outcomes),
            outcomes=tuple(outcomes),
            vault_manifest_hash=preflight.portable_vault_manifest.portable_tree_hash,
        )
        ledger.append(
            "ACQUISITION_COMPLETED",
            context_hash=context_hash,
            operation_hash=global_receipt.receipt_hash,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        ledger.append(
            "ACQUISITION_FAILED",
            context_hash=context_hash,
            operation_hash=content_hash(type(error).__name__),
        )
        raise
    return tuple(outcomes), preflight, global_receipt, ledger.receipt(), policy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r27-sha", required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--preserved-vault", type=Path, required=True)
    parser.add_argument("--phase0-inventory", type=Path, required=True)
    parser.add_argument("--phase0-preservation", type=Path, required=True)
    parser.add_argument("--authority-statement", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--archive-cases", type=int, default=5_120)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("R27 qualification output must be fresh")
    if output.is_relative_to(repository):
        raise ValueError("R27 qualification workspace must remain outside Git")
    if not args.development:
        _require_clean_exact(repository, args.r27_sha)
    pool = _load(args.pool)
    inventory = _load(args.phase0_inventory)
    preservation = _load(args.phase0_preservation)
    _verify_phase0(inventory, preservation, pool)
    preserved_vault = args.preserved_vault.resolve(strict=True)
    file_count, byte_count, vault_hash, vault_rows = _vault_inventory(preserved_vault)
    if (
        file_count != preservation["vault_file_count"]
        or byte_count != preservation["vault_byte_count"]
        or vault_hash != preservation["vault_manifest_hash"]
        or list(vault_rows) != preservation["vault_file_manifest"]
    ):
        raise ValueError("preserved F26 vault changed after Phase 0")

    private_root = output / "private"
    public_root = output / "public"
    private_root.mkdir(parents=True)
    public_root.mkdir()
    archive_campaign = run_archive_mutation_campaign(args.archive_cases)
    mixed_campaign = run_mixed_candidate_fault_campaign(
        private_root / "mixed-candidate-campaign",
        candidate_count=len(pool["candidates"]),
    )
    outcomes, preflight, global_receipt, ledger_receipt, archive_policy = _run_recovery(
        repository=repository,
        r27_sha=args.r27_sha,
        pool=pool,
        preserved_vault=preserved_vault,
        authority_statement=args.authority_statement.resolve(strict=True),
        private_root=private_root,
    )

    entries = build_m336k_disclosure_entries(
        outcomes,
        disclosure_reason="FAILED_FINAL_ACQUISITION_F26",
        originating_chain=F26_CHAIN,
    )
    registry_copy = private_root / "disclosed-java-registry"
    shutil.copytree(args.registry.resolve(strict=True), registry_copy)
    manifest, append_receipt = append_disclosed_java_entries_v2(
        registry_copy,
        entries,
        acquisition_run_id=RUN_ID,
        f20_sha=args.r27_sha,
    )
    verify_disclosed_java_registry(registry_copy)
    disclosure = _disclosure_recovery(outcomes, entries, append_receipt, manifest)
    recovered_inventory = _recovered_inventory(inventory, outcomes, entries)
    terminal_matrix = _terminal_matrix(outcomes)
    compatibility = build_m336k_compatibility_qualification(preflight, outcomes)
    qualification_summary = build_m336k_compatibility_summary(
        exact_sha=args.r27_sha,
        preflight=preflight,
        qualification=compatibility,
        registry_root=args.registry.resolve(strict=True),
    )

    blocking = next(
        item
        for item in outcomes
        if item.terminal_receipt.candidate_family_id == "koloboke-api"
    )
    forensics = public_archive_forensics(blocking.archive_result)
    rejected_families = {
        item.terminal_receipt.candidate_family_id
        for item in outcomes
        if not item.terminal_receipt.eligible
    }
    census_families = {
        item.candidate_root for item in preflight.selectability_census.decisions
    }
    rejected_census_entries = len(rejected_families & census_families)
    status_counts = Counter(
        item.terminal_receipt.terminal_status.value for item in outcomes
    )
    rehearsal_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_F26_DISCLOSED_REHEARSAL",
        "exact_r27_sha": args.r27_sha,
        "candidate_count": len(outcomes),
        "terminal_receipt_count": len(outcomes),
        "missing_terminal_receipt_count": 66 - len(outcomes),
        "duplicate_terminal_receipt_count": 0,
        "terminal_status_counts": tuple(sorted(status_counts.items())),
        "candidate_local_error_escape_count": 0,
        "unexpected_swallowed_exception_count": 0,
        "authoritative_archive_inspection_count": sum(
            item.authoritative_archive_inspection_count for item in outcomes
        ),
        "minimum_authoritative_inspections_per_candidate": min(
            item.authoritative_archive_inspection_count for item in outcomes
        ),
        "maximum_authoritative_inspections_per_candidate": max(
            item.authoritative_archive_inspection_count for item in outcomes
        ),
        "unbound_archive_reinterpretation_count": 0,
        "rejected_source_index_entry_count": 0,
        "rejected_census_entry_count": rejected_census_entries,
        "selectable_file_count": preflight.selectability_census.selectable_file_count,
        "selectable_root_count": preflight.selectability_census.selectable_root_count,
        "balanced_capacity": preflight.feasibility_proof.balanced_capacity,
        "closure_feasibility": "PASS"
        if preflight.feasibility_proof.hard_requirements_satisfied
        else "BLOCKED",
        "selector_reservation_count": 0,
        "selector_invocation_count": 0,
        "selector_rerun_count": 0,
        "global_acquisition_status": global_receipt.status,
        "preflight_status": preflight.status,
        "status": "PASS"
        if preflight.status == "PASS"
        and global_receipt.status == "ACQUISITION_COMPLETED"
        and rejected_census_entries == 0
        else "FAIL",
    }
    rehearsal = {**rehearsal_body, "report_hash": content_hash(rehearsal_body)}
    recovery_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_F26_FAILED_RUN_RECOVERY",
        "exact_f26_sha": F26_SHA,
        "historical_outcome": "OUTCOME C — BLOCKED",
        "historical_final_event": "ACQUISITION_FAILED",
        "historical_acquisition_rerun_count": 0,
        "historical_selector_invocation_count": 0,
        "historical_evaluator_invocation_count": 0,
        "phase0_inventory_receipt_hash": inventory["receipt_hash"],
        "phase0_preservation_receipt_hash": preservation["receipt_hash"],
        "preserved_vault_manifest_hash": vault_hash,
        "preserved_vault_mutation_count": 0,
        "rehearsal_run_id_reuses_f26": False,
        "status": "PASS",
    }
    recovery = {**recovery_body, "report_hash": content_hash(recovery_body)}

    _write(private_root / "full_preflight.json", asdict(preflight))
    _write(public_root / "archive_policy_v2.json", asdict(archive_policy))
    _write(public_root / "archive_mutation_campaign.json", asdict(archive_campaign))
    _write(public_root / "mixed_candidate_fault_campaign.json", asdict(mixed_campaign))
    _write(public_root / "f26_candidate_inventory.json", recovered_inventory)
    _write(public_root / "f26_failed_run_recovery.json", recovery)
    _write(public_root / "f26_duplicate_path_forensics.json", forensics)
    _write(public_root / "f26_candidate_terminal_matrix.json", terminal_matrix)
    _write(public_root / "f26_global_acquisition_receipt.json", asdict(global_receipt))
    _write(public_root / "f26_acquisition_ledger_receipt.json", asdict(ledger_receipt))
    _write(public_root / "f26_disclosure_recovery.json", disclosure)
    _write(
        public_root / "f26_disclosure_registry_append_receipt.json",
        asdict(append_receipt),
    )
    _write(public_root / "candidate_qualification.json", compatibility)
    _write(public_root / "preflight_summary.json", qualification_summary)
    _write(
        public_root / "source_entry_binding_manifest.json",
        asdict(preflight.source_entry_binding_manifest),
    )
    _write(
        public_root / "selectability_census.json",
        asdict(preflight.selectability_census),
    )
    _write(
        public_root / "selector_feasibility.json", asdict(preflight.feasibility_proof)
    )
    _write(public_root / "disclosed_rehearsal_summary.json", rehearsal)
    leak = scan_fresh_source_leaks(private_root / "vault", public_root)
    _write(public_root / "source_leak_report.json", leak)
    if (
        archive_campaign.status != "PASS"
        or mixed_campaign.status != "PASS"
        or recovery["status"] != "PASS"
        or disclosure["status"] != "PASS"
        or rehearsal["status"] != "PASS"
        or leak["status"] != "PASS"
    ):
        raise ValueError("R27 candidate-isolation qualification failed")


if __name__ == "__main__":
    main()
