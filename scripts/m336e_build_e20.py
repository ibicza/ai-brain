"""Derive exact M-33.6e E20 public evidence and readiness from primary receipts."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_contracts import (
    M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    produce_m336e_independent_evaluation,
    produce_m336e_readiness,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: dict) -> bytes:
    raw = (canonical_json(value) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _quality_passed(value: dict) -> bool:
    return value.get("status") == "PASS" and all(
        value.get(name) is True
        for name in (
            "ruff_format_pass",
            "ruff_lint_pass",
            "targeted_pass",
            "no_torch_network_pass",
            "java_reference_compile_pass",
            "full_suite_pass",
            "clean_worktree",
            "head_upstream_equal",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-h20", required=True)
    parser.add_argument("--q20-summary", type=Path, required=True)
    parser.add_argument("--f20-root", type=Path, required=True)
    parser.add_argument("--h20-root", type=Path, required=True)
    parser.add_argument("--windows-evaluation", type=Path, required=True)
    parser.add_argument("--karina-evaluation", type=Path, required=True)
    parser.add_argument("--evaluation-comparison", type=Path, required=True)
    parser.add_argument("--evaluation-completion", type=Path, required=True)
    parser.add_argument("--security", type=Path, required=True)
    parser.add_argument("--performance", type=Path, required=True)
    parser.add_argument("--contract-gate", type=Path, required=True)
    parser.add_argument("--source-leak", type=Path, required=True)
    parser.add_argument("--quality", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    if (
        _git(repository, "rev-parse", "HEAD^{commit}") != args.expected_h20
        or len(args.expected_h20) != 40
        or _git(repository, "status", "--porcelain=v1")
    ):
        raise ValueError("E20 assembly requires a clean exact-H20 worktree")
    if args.output.exists() or args.receipt.exists():
        raise FileExistsError("fresh E20 assembly outputs must not exist")

    q20 = _load(args.q20_summary.resolve(strict=True))
    f20 = args.f20_root.resolve(strict=True)
    pool = _load(f20 / "candidate_pool.json")
    windows_cache = _load(f20 / "local_cache_windows.json")
    karina_cache = _load(f20 / "local_cache_karina.json")
    freeze = _load(f20 / "m336e_freeze_manifest.json")
    h20 = args.h20_root.resolve(strict=True)
    acquisition = _load(h20 / "acquisition_receipts.json")
    qualification = _load(h20 / "qualification_summary.json")
    vault = _load(h20 / "portable_vault_summary.json")
    selectability = _load(h20 / "selectability_summary.json")
    selector = _load(h20 / "selector_receipt.json")
    registry = _load(h20 / "disclosure_registry_append_receipt.json")
    protocol = _load(h20 / "protocol_ledger_receipt.json")
    production = _load(h20 / "production_summary.json")
    pack = _load(h20 / "candidate_pack_receipt.json")
    seal = _load(h20 / "h20_seal.json")
    windows = _load(args.windows_evaluation.resolve(strict=True))
    karina = _load(args.karina_evaluation.resolve(strict=True))
    comparison = _load(args.evaluation_comparison.resolve(strict=True))
    completion = _load(args.evaluation_completion.resolve(strict=True))
    security = _load(args.security.resolve(strict=True))
    performance = _load(args.performance.resolve(strict=True))
    contract = _load(args.contract_gate.resolve(strict=True))
    leak = _load(args.source_leak.resolve(strict=True))
    qualities = tuple(_load(path.resolve(strict=True)) for path in args.quality)

    for name in (
        "acquisition_receipts.json",
        "qualification_summary.json",
        "portable_vault_summary.json",
        "selectability_summary.json",
        "selector_receipt.json",
        "disclosure_registry_append_receipt.json",
        "protocol_ledger_receipt.json",
        "production_summary.json",
        "candidate_pack_receipt.json",
        "h20_seal.json",
    ):
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            f"h20/{name}", (h20 / name).read_bytes()
        )

    neutral_evaluation_fields = (
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
    evaluations_equal = all(
        windows[name] == karina[name] for name in neutral_evaluation_fields
    )
    leak_count = leak.get("fresh_source_leak_count", leak.get("source_leak_count"))
    if leak_count is None:
        raise ValueError("source-leak receipt lacks its aggregate denominator")
    selected_roots = selector["selected_root_count"]
    criteria = (
        ("q20_disclosed_full_path", q20.get("status") == "PASS"),
        ("fresh_pool_family_count", pool["candidate_count"] >= 48),
        ("fresh_pool_organization_count", pool["organization_count"] >= 40),
        (
            "fresh_pool_organization_cap",
            pool["maximum_candidates_per_organization"] <= 2,
        ),
        ("fresh_pool_required_zero", pool["required_candidate_count"] == 0),
        (
            "fresh_pool_all_optional",
            pool["optional_candidate_count"] == pool["candidate_count"],
        ),
        ("pre_f20_source_body_zero", freeze["pre_f20_source_body_bytes_received"] == 0),
        ("windows_cache_body_read_zero", windows_cache["source_body_bytes_read"] == 0),
        ("karina_cache_body_read_zero", karina_cache["source_body_bytes_read"] == 0),
        ("global_acquisition_once", acquisition["global_acquisition_count"] == 1),
        (
            "all_frozen_candidates_acquired",
            acquisition["candidate_count"] == pool["candidate_count"],
        ),
        ("vault_physical_equal", vault["physical_difference_count"] == 0),
        ("vault_manifest_equal", vault["canonical_manifest_difference_count"] == 0),
        ("vault_tree_equal", vault["portable_tree_hash_difference_count"] == 0),
        ("freshness_overlap_zero", qualification["freshness_overlap_count"] == 0),
        (
            "all_candidates_qualified",
            len(qualification["candidate_decisions"]) == acquisition["candidate_count"],
        ),
        ("raw_publication_denied", qualification["raw_publication_root_count"] == 0),
        (
            "excerpt_publication_denied",
            qualification["excerpt_publication_root_count"] == 0,
        ),
        (
            "derived_publication_covers_selected",
            qualification["derived_pack_publication_root_count"] >= selected_roots,
        ),
        (
            "metrics_publication_covers_selected",
            qualification["metrics_publication_root_count"] >= selected_roots,
        ),
        ("selectable_roots", selectability["selectable_root_count"] >= 3),
        ("selectable_files", selectability["selectable_file_count"] >= 180),
        ("balanced_capacity", selectability["balanced_capacity"] >= 180),
        ("selector_target_frozen", selectability["target_file_count"] == 180),
        ("selector_root_cap_frozen", selectability["maximum_files_per_root"] == 63),
        ("selector_invocation_once", selector["selector_invocation_count"] == 1),
        ("selector_rerun_zero", selector["selector_rerun_count"] == 0),
        ("selected_files_exact", selector["selected_file_count"] == 180),
        ("selected_roots_minimum", selected_roots >= 3),
        ("selected_root_cap", selector["maximum_one_root_count"] <= 63),
        ("selector_evaluator_reads_zero", selector["evaluator_read_count"] == 0),
        ("selector_golden_reads_zero", selector["golden_read_count"] == 0),
        ("selector_trust_reads_zero", selector["trust_metric_read_count"] == 0),
        ("ledger_acquisition_once", protocol["global_acquisition_count"] == 1),
        ("ledger_census_once", protocol["selectability_census_count"] == 1),
        ("ledger_selector_once", protocol["selector_invocation_count"] == 1),
        ("ledger_selector_rerun_zero", protocol["selector_rerun_count"] == 0),
        ("ledger_two_production_seals", protocol["production_seal_count"] == 2),
        ("ledger_evaluator_once", protocol["evaluator_start_count"] == 1),
        ("production_platform_equal", production["platform_difference_count"] == 0),
        ("production_proposals_nonempty", production["proposal_count"] > 0),
        ("production_trusted_nonempty", production["trusted_count"] > 0),
        ("post_trust_failures_zero", production["post_trust_pack_failure_count"] == 0),
        ("production_evaluator_reads_zero", production["evaluator_read_count"] == 0),
        ("production_golden_reads_zero", production["golden_read_count"] == 0),
        ("production_network_zero", production["network_access_count"] == 0),
        ("candidate_pack_compiles", pack["compiled"] is True),
        ("candidate_pack_replays", pack["replay_status"] == "PASS"),
        (
            "registry_append_complete",
            registry["resulting_entry_count"]
            == registry["previous_entry_count"] + registry["appended_entry_count"],
        ),
        (
            "producer_contract_closed",
            contract.get("status") == "PASS"
            and contract["uncontracted_produced_artifact_count"] == 0,
        ),
        ("fresh_leaks_zero", leak_count == 0),
        (
            "h20_public_seal",
            seal["producer_contract_failure_count"] == 0
            and seal["source_leak_count"] == 0,
        ),
        (
            "evaluation_platform_equal",
            evaluations_equal
            and comparison["platform_independent_difference_count"] == 0,
        ),
        (
            "spdx_agreement",
            windows["production_reference_license_agreement"] == "1.000000",
        ),
        (
            "spdx_false_identities_zero",
            windows["false_automatic_license_identity_count"] == 0,
        ),
        (
            "selected_license_disagreements_zero",
            windows["selected_root_unresolved_disagreement_count"] == 0,
        ),
        (
            "semantic_location",
            windows["location_precision"] == "1.000000"
            and windows["location_recall"] >= "0.950000",
        ),
        (
            "semantic_meaning",
            windows["semantic_precision"] == "1.000000"
            and windows["semantic_recall"] >= "0.950000",
        ),
        (
            "semantic_trust",
            windows["trust_precision"] == "1.000000"
            and windows["trust_coverage"] >= "0.850000",
        ),
        ("field_evidence_exact", windows["field_evidence_exactness"] == "1.000000"),
        ("resolution_agreement", windows["resolution_agreement"] == "1.000000"),
        ("wrong_trusted_zero", windows["wrong_trusted_count"] == 0),
        (
            "evaluation_pack_integrity",
            windows["post_trust_pack_failures"] == 0
            and windows["candidate_pack_compiled"] is True
            and windows["candidate_replay_status"] == "PASS",
        ),
        (
            "installed_runtime",
            windows["runtime_status"] == "PASS"
            and windows["runtime_network_access_count"] == 0,
        ),
        (
            "evaluation_completed",
            completion["status"] == "PASS"
            and completion["protocol_ledger_receipt"]["final_event_type"]
            == "EVALUATION_COMPLETED",
        ),
        ("security_regressions", security.get("status") == "PASS"),
        ("performance_measured", performance.get("status") == "PASS"),
        (
            "quality_all_platforms",
            len(qualities) >= 2 and all(_quality_passed(item) for item in qualities),
        ),
    )
    variant = "SUCCESS" if all(value for _name, value in criteria) else "BLOCKED"
    evaluation = produce_m336e_independent_evaluation(variant, evaluation=windows)
    readiness = produce_m336e_readiness(variant, criteria=criteria)

    args.output.mkdir(parents=True)
    evaluation_raw = _write(args.output / "evaluation.json", evaluation)
    readiness_raw = _write(args.output / "readiness.json", readiness)
    validations = (
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "e20/evaluation.json", evaluation_raw
        ),
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "e20/readiness.json", readiness_raw
        ),
    )
    evidence_rows = tuple(
        sorted(
            (
                path.name,
                bytes_hash(path.read_bytes()),
            )
            for path in args.output.iterdir()
            if path.is_file()
        )
    )
    receipt_body = {
        "schema_version": 2,
        "h20_sha": args.expected_h20,
        "f20_sha": freeze.get("f20_sha", acquisition["f20_sha"]),
        "criterion_count": len(criteria),
        "passed_criterion_count": sum(value for _name, value in criteria),
        "criteria": criteria,
        "contract_validation_hashes": tuple(
            item.validation_hash for item in validations
        ),
        "e20_public_tree_hash": content_hash(evidence_rows),
        "outcome": readiness["outcome"],
        "status": "PASS" if variant == "SUCCESS" else "BLOCKED",
    }
    _write(args.receipt, {**receipt_body, "receipt_hash": content_hash(receipt_body)})
    if variant != "SUCCESS":
        raise SystemExit("M-33.6e E20 readiness is OUTCOME_C")


if __name__ == "__main__":
    main()
