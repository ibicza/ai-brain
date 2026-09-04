"""Independently derive M-33.6c readiness from raw measured reports."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336c_readiness import (
    build_m336c_raw_report,
    evaluate_m336c_readiness,
    verify_m336c_readiness,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--cross-platform", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh M-33.6c readiness output already exists")
    development = args.development.resolve(strict=True)
    production = args.production.resolve(strict=True)
    evaluation = args.evaluation.resolve(strict=True)
    license_report = _load(development / "independent_license_evaluation.json")
    forensics = _load(development / "license_forensics.json")
    authority = _load(development / "candidate_authority.json")
    selector = _load(development / "selector_receipt.json")
    scope = _load(development / "source_scope_invariant.json")
    security = _load(development / "security_report.json")
    production_summary = _load(production / "production_summary.json")
    production_counts = _load(production / "production_counts.json")
    replay = _load(production / "candidate_replay.json")
    evaluated = _load(evaluation / "evaluation_summary.json")
    runtime = _load(evaluation / "runtime_proof.json")
    h17 = _load(development / "h17_contract_forensics.json")
    hypothetical = _load(development / "hypothetical_h_stage_contract.json")
    mutations = _load(development / "contract_mutations.json")
    quality = _load(args.quality.resolve(strict=True))
    cross_platform = _load(args.cross_platform.resolve(strict=True))
    raw_publication_roots = sum(
        any(
            item["target"] == "RAW_SOURCE_PUBLICATION" and item["status"] == "ELIGIBLE"
            for item in candidate["authority"]["publication"]
        )
        for candidate in authority
    )
    reports = (
        build_m336c_raw_report(
            "license_matching",
            {
                "precision": license_report["automatically_trusted_precision"],
                "false_apache_matches": license_report["false_apache_match_count"],
                "optional_variants_rejected": license_report[
                    "optional_apache_variant_rejected_count"
                ],
                "true_conflict_mutations": license_report[
                    "true_conflict_mutation_count"
                ],
                "true_conflict_mutations_blocked": license_report[
                    "true_conflict_mutation_blocked_count"
                ],
            },
        ),
        build_m336c_raw_report(
            "evidence_fusion",
            {
                "old_conflicts": forensics["historical_conflict_count"],
                "classified_old_conflicts": forensics["historical_conflict_count"]
                - forensics["unclassified_historical_conflict_count"],
                "false_candidate_conflicts": sum(
                    item["authority"]["license_fusion_status"]
                    == "TRUE_LICENSE_CONFLICT"
                    for item in authority
                ),
            },
        ),
        build_m336c_raw_report(
            "document_roles",
            {
                "document_count": sum(len(item["documents"]) for item in authority),
                "unresolved_role_count": forensics["unresolved_document_role_count"],
            },
        ),
        build_m336c_raw_report(
            "source_use",
            {
                "authority_axes_separate": all(
                    {
                        "source_authenticity",
                        "knowledge_acquisition",
                        "source_use_scopes",
                        "publication",
                    }
                    <= set(item["authority"])
                    and len(item["authority"]["publication"]) == 4
                    for item in authority
                ),
                "local_does_not_imply_publication": raw_publication_roots == 0
                and all(
                    "PRIVATE_LOCAL_ANALYSIS" in item["authority"]["source_use_scopes"]
                    for item in authority
                ),
                "scope_semantic_hash_equal": scope["semantic_content_hashes_equal"],
                "model_created_approvals_accepted": security[
                    "model_created_publication_approvals_accepted"
                ],
            },
        ),
        build_m336c_raw_report(
            "candidate_qualification",
            {
                "candidate_count": len(authority),
                "typed_candidate_count": sum(
                    bool(item["authority"]["decision_hash"]) for item in authority
                ),
                "analysis_eligible_root_count": sum(
                    item["authority"]["knowledge_acquisition"]
                    == "ELIGIBLE_FOR_ANALYSIS"
                    for item in authority
                ),
                "publication_eligible_root_count": raw_publication_roots,
                "candidate_specific_branch_count": security[
                    "candidate_specific_branch_count"
                ],
            },
        ),
        build_m336c_raw_report(
            "selector",
            {
                "invocation_count": selector["selector_invocation_count"],
                "rerun_count": selector["selector_rerun_count"],
            },
        ),
        build_m336c_raw_report(
            "java_production",
            {
                "completed": production_summary["status"] == "PASS",
                "proposal_count": production_counts["proposal_count"],
                "post_trust_pack_failures": production_counts[
                    "post_trust_pack_failures"
                ],
                "evaluator_dependency_count": production_summary[
                    "production_evaluator_dependency_count"
                ],
                "golden_read_count": production_summary["production_golden_read_count"],
            },
        ),
        build_m336c_raw_report(
            "candidate_replay",
            {
                "compiled": bool(production_summary["candidate_pack_hash"]),
                "replay_without_evaluator": replay["status"] == "PASS",
            },
        ),
        build_m336c_raw_report(
            "evaluator",
            {
                "ran_after_production_seal": evaluated[
                    "production_sealed_before_evaluator"
                ],
                "location_precision": evaluated["location_precision"],
                "location_recall": evaluated["location_recall"],
                "semantic_precision": evaluated["semantic_precision"],
                "semantic_recall": evaluated["semantic_recall"],
                "trust_precision": evaluated["trust_precision"],
                "trust_coverage": evaluated["trust_coverage"],
                "wrong_trusted_count": evaluated["wrong_trusted_count"],
                "field_evidence_exactness": evaluated["field_evidence_exactness"],
                "resolution_agreement": evaluated["resolution_agreement"],
            },
        ),
        build_m336c_raw_report(
            "runtime",
            {
                "installed": evaluated["runtime_status"] == "PASS",
                "runtime_queries_pass": runtime["status"] == "PASS",
                "no_network": runtime.get("runtime_process_audit", {}).get(
                    "socket_attempts", 0
                )
                == 0,
            },
        ),
        build_m336c_raw_report(
            "artifact_contract",
            {
                "h17_unknown_paths": h17["unknown_path_count"],
                "h17_unclassified_fields": h17["unclassified_field_count"],
                "h17_missing_fields": h17["missing_mandatory_field_count"],
                "h17_unexpected_fields": h17["unexpected_field_count"],
                "h17_role_mismatches": h17["role_mismatch_count"],
                "hypothetical_unknown_paths": hypothetical["unknown_path_count"],
                "hypothetical_missing_roles": hypothetical[
                    "missing_role_binding_count"
                ],
                "hypothetical_missing_fields": hypothetical[
                    "missing_protected_field_count"
                ],
                "hypothetical_extra_fields": hypothetical[
                    "extra_protected_field_count"
                ],
                "disclosure_claim_mismatches": hypothetical[
                    "disclosure_claim_mismatch_count"
                ],
            },
        ),
        build_m336c_raw_report(
            "disclosure_mutations",
            {
                "mutation_count": mutations["mutation_count"],
                "rejected_count": mutations["rejected_count"],
                "accepted_count": mutations["accepted_count"],
            },
        ),
        build_m336c_raw_report("formatting_tests", quality),
        build_m336c_raw_report(
            "cross_platform",
            {
                "platform_independent_difference_count": cross_platform[
                    "platform_independent_difference_count"
                ]
            },
        ),
    )
    gate = evaluate_m336c_readiness(reports)
    verify_m336c_readiness(reports, gate)
    args.output.mkdir(parents=True)
    for report in reports:
        _write(args.output / "raw" / f"{report.report_type}.json", asdict(report))
    _write(args.output / "readiness_gate.json", asdict(gate))


if __name__ == "__main__":
    main()
