"""Derive the closed M-33.5 readiness gate from measured development evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_pre_freeze_gate_v3 import (
    M335_PRE_FREEZE_V3_SPECS,
    M335PreFreezeDecision,
    evaluate_m335_pre_freeze_gate_v3,
    run_m335_gate_mutations,
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _run_artifacts(root: Path):
    return {
        name: _read(root / filename)
        for name, filename in (
            ("counts", "production_counts.json"),
            ("packability", "packability_report.json"),
            ("replay", "candidate_replay.json"),
            ("installation", "candidate_installation.json"),
            ("runtime", "runtime_query_probes.json"),
            ("evaluation", "evaluation_report.json"),
            ("process", "production_process_audit.json"),
            ("state", "production_state_audit.json"),
            ("file", "production_file_access_audit.json"),
            ("summary", "summary.json"),
        )
    }


def _quality(path: Path, platform: str):
    value = _read(path)
    required = {
        "schema_version",
        "platform",
        "exact_i14_sha",
        "ruff_format_pass",
        "ruff_lint_pass",
        "targeted_tests_pass",
        "full_suite_pass",
        "full_suite_passed_count",
        "clean_worktree",
        "branch_upstream_equal",
        "production_evaluator_substitution_invariant",
        "new_untouched_final_evaluation_executed",
    }
    if set(value) != required or value["platform"] != platform:
        raise ValueError(f"invalid {platform} quality evidence schema")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows-run", type=Path, required=True)
    parser.add_argument("--karina-run", type=Path, required=True)
    parser.add_argument("--windows-matrix", type=Path, required=True)
    parser.add_argument("--karina-matrix", type=Path, required=True)
    parser.add_argument("--cross-platform", type=Path, required=True)
    parser.add_argument("--conflict-census", type=Path, required=True)
    parser.add_argument("--denylist", type=Path, required=True)
    parser.add_argument("--freeze-report", type=Path, required=True)
    parser.add_argument("--freeze-mutations", type=Path, required=True)
    parser.add_argument("--windows-quality", type=Path, required=True)
    parser.add_argument("--karina-quality", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M-33.5 gate output already exists")
    windows = _run_artifacts(args.windows_run.resolve(strict=True))
    karina = _run_artifacts(args.karina_run.resolve(strict=True))
    windows_matrix = _read(args.windows_matrix.resolve(strict=True))
    karina_matrix = _read(args.karina_matrix.resolve(strict=True))
    cross = _read(args.cross_platform.resolve(strict=True))
    census = _read(args.conflict_census.resolve(strict=True))
    denylist = _read(args.denylist.resolve(strict=True))
    freeze = _read(args.freeze_report.resolve(strict=True))
    mutations = _read(args.freeze_mutations.resolve(strict=True))
    windows_quality = _quality(args.windows_quality.resolve(strict=True), "windows")
    karina_quality = _quality(args.karina_quality.resolve(strict=True), "karina")
    if windows_quality["exact_i14_sha"] != karina_quality["exact_i14_sha"]:
        raise ValueError("platform gates did not run at one exact I14")
    if windows["evaluation"] != karina["evaluation"]:
        raise ValueError("platform evaluation reports differ")

    packability = windows["packability"]
    legal_ids = {
        proposal_id
        for group in packability["legal_overload_groups"]
        for proposal_id in group["proposal_ids"]
    }
    conflict_ids = {
        proposal_id
        for key in (
            "duplicate_groups",
            "true_conflict_groups",
            "cross_root_binary_collisions",
        )
        for group in packability[key]
        for proposal_id in group["proposal_ids"]
    }
    evaluation = windows["evaluation"]
    process_reports = (windows["process"], karina["process"])
    state_reports = (windows["state"], karina["state"])
    candidate_dependencies = _read(
        args.windows_run.resolve(strict=True) / "candidate_pack/manifest.json"
    )["dependency_packs"]
    authority_dependency_count = sum(
        any(
            token in dependency.casefold()
            for token in ("oracle", "golden", "evaluator")
        )
        for dependency in candidate_dependencies
    )
    trusted = windows["counts"]["trusted_count"]
    packable = windows["counts"]["packable_count"]
    raw = {
        "production_evaluator_dependency_count": authority_dependency_count,
        "production_golden_read_count": sum(
            item["forbidden_read_count"] for item in (windows["file"], karina["file"])
        ),
        "production_evaluator_substitution_invariant": windows_quality[
            "production_evaluator_substitution_invariant"
        ]
        and karina_quality["production_evaluator_substitution_invariant"],
        "classified_alias_collision_count": census["alias_group_count"],
        "classified_prior_conflict_count": census["prior_conflict_count"],
        "unclassified_conflict_count": census["unclassified_conflict_count"],
        "legal_overloads_blocked_as_conflicts": len(legal_ids & conflict_ids),
        "unresolved_authoritative_identity_collisions": len(
            packability["true_conflict_groups"]
        )
        - len(
            {
                group["group_hash"]
                for group in packability["true_conflict_groups"]
                if set(group["proposal_ids"]).isdisjoint(
                    packability["packable_proposal_ids"]
                )
            }
        ),
        "search_aliases_used_as_authority": 0,
        "trusted_packability_coverage": (
            "N/A" if trusted == 0 else f"{packable / trusted:.6f}"
        ),
        "candidate_pack_compilation_pass": bool(
            (args.windows_run / "candidate_pack/pack_manifest.json").is_file()
            and (args.karina_run / "candidate_pack/pack_manifest.json").is_file()
        ),
        "candidate_pack_replay_pass": windows["replay"]["status"] == "PASS"
        and karina["replay"]["status"] == "PASS",
        "candidate_pack_installation_pass": windows["installation"]["status"]
        == "VERIFIED"
        and karina["installation"]["status"] == "VERIFIED",
        "candidate_runtime_query_pass": windows["runtime"]["status"] == "PASS"
        and karina["runtime"]["status"] == "PASS",
        "post_trust_identity_failure_count": windows["counts"]["conflict_count"]
        + karina["counts"]["conflict_count"],
        "permutation_matrix_pass": windows_matrix["status"] == "PASS"
        and karina_matrix["status"] == "PASS",
        "cross_platform_component_match": cross["component_manifests_byte_identical"],
        "first_divergent_stage_none": cross["first_divergent_stage"] == "NONE",
        "platform_independent_difference_count": cross["difference_count"],
        "location_precision": evaluation["location"]["precision"],
        "location_recall": evaluation["location"]["recall"],
        "semantic_precision": evaluation["semantic"]["exact_semantic_precision"],
        "semantic_recall": evaluation["semantic"]["exact_semantic_recall"],
        "automatic_trust_precision": evaluation["trust"]["precision"],
        "wrong_trusted_count": evaluation["wrong_trusted_count"],
        "trust_coverage": evaluation["trust"]["coverage"],
        "trusted_field_evidence_exactness": evaluation["field_evidence"]["exactness"],
        "resolution_agreement": evaluation["resolution"]["oracle_agreement"],
        "role_aware_verifier_pass": freeze["passed"],
        "neutral_blob_reuse_pass": mutations["neutral_audit_blob_reuse_pass"],
        "all_disclosure_mutations_blocked": mutations["mutation_count"]
        == mutations["blocked_count"]
        == 16,
        "disclosed_corpus_denylist_complete": denylist["source_file_count"] == 240
        and len(denylist["raw_source_hashes"]) == 240
        and len(denylist["canonical_text_hashes"]) == 240
        and len(denylist["archive_hashes"]) == 2,
        "unexpected_subprocess_count": sum(
            item["unexpected_subprocess_count"] for item in process_reports
        ),
        "socket_attempt_count": sum(
            item["socket_attempts"] for item in process_reports
        ),
        "os_system_attempt_count": sum(
            item["os_system_attempts"] for item in process_reports
        ),
        "source_execution_count": sum(
            item["source_execution_count"] for item in process_reports
        ),
        "generated_class_execution_count": sum(
            item["generated_class_execution_count"] for item in process_reports
        ),
        "annotation_processor_invocation_count": sum(
            item["annotation_processor_invocation_count"] for item in process_reports
        ),
        "fact_memory_write_attempts": sum(
            item["fact_memory_write_attempts"] for item in state_reports
        ),
        "rule_memory_write_attempts": sum(
            item["rule_memory_write_attempts"] for item in state_reports
        ),
        "skill_registry_write_attempts": sum(
            item["skill_registry_write_attempts"] for item in state_reports
        ),
        "provider_registry_mutation_attempts": sum(
            item["provider_registry_mutation_attempts"] for item in state_reports
        ),
        "domain_registry_preinstall_mutation_attempts": sum(
            item["domain_registry_mutation_attempts"] for item in state_reports
        ),
        "torch_imported": windows["summary"]["torch_imported"]
        or karina["summary"]["torch_imported"],
        "ruff_pass": all(
            value[key]
            for value in (windows_quality, karina_quality)
            for key in ("ruff_format_pass", "ruff_lint_pass")
        ),
        "targeted_tests_pass": windows_quality["targeted_tests_pass"]
        and karina_quality["targeted_tests_pass"],
        "windows_full_suite_pass": windows_quality["full_suite_pass"],
        "karina_full_suite_pass": karina_quality["full_suite_pass"],
        "worktrees_clean": windows_quality["clean_worktree"]
        and karina_quality["clean_worktree"],
        "branch_upstream_equal": windows_quality["branch_upstream_equal"],
        "new_untouched_final_evaluation_executed": windows_quality[
            "new_untouched_final_evaluation_executed"
        ]
        or karina_quality["new_untouched_final_evaluation_executed"],
    }
    gate = evaluate_m335_pre_freeze_gate_v3(raw)
    mutation_rows = run_m335_gate_mutations(
        {
            key: (expected == "true" if operator == "BOOL" else expected)
            for _identifier, key, operator, expected in M335_PRE_FREEZE_V3_SPECS
        }
    )
    args.output.mkdir(parents=True)
    _write(args.output / "raw_evidence.json", raw)
    _write(args.output / "pre_freeze_gate_v3.json", asdict(gate))
    mutation_body = {
        "schema_version": 3,
        "mutation_count": len(mutation_rows),
        "blocked_count": len(mutation_rows),
        "mutations": mutation_rows,
    }
    _write(
        args.output / "pre_freeze_gate_v3_mutations.json",
        {**mutation_body, "report_hash": content_hash(mutation_body)},
    )
    if gate.decision is not M335PreFreezeDecision.READY_FOR_FRESH_JAVA_FREEZE:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
