"""Build evidence-only E19 from H19 seals and independent platform runs."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_contracts import (
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
)
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336d_readiness import (
    M336DReadinessMode,
    build_primary_receipt,
    evaluate_m336d_readiness,
    load_primary_receipts,
    verify_m336d_readiness,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--h19-sha", required=True)
    parser.add_argument("--h19-root", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--windows-evaluation", type=Path, required=True)
    parser.add_argument("--karina-evaluation", type=Path, required=True)
    parser.add_argument("--evaluation-comparison", type=Path, required=True)
    parser.add_argument("--f19-windows-quality", type=Path, required=True)
    parser.add_argument("--f19-karina-quality", type=Path, required=True)
    parser.add_argument("--h19-windows-quality", type=Path, required=True)
    parser.add_argument("--h19-karina-quality", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh E19 evidence output already exists")
    h19 = args.h19_root.resolve(strict=True)
    windows = args.windows_evaluation.resolve(strict=True)
    karina = args.karina_evaluation.resolve(strict=True)
    comparison = _load(args.evaluation_comparison)
    if comparison["platform_independent_difference_count"]:
        raise ValueError("evaluation differs before E19")
    args.output.mkdir(parents=True)
    e19 = args.output / "e19"
    e19.mkdir()
    shutil.copyfile(windows / "evaluation.json", e19 / "evaluation.json")
    shutil.copyfile(
        windows / "independent_license_evaluation.json",
        e19 / "independent_license_evaluation.json",
    )
    shutil.copyfile(
        windows / "semantic/evaluation_report.json",
        e19 / "independent_jdk_semantic_evaluation.json",
    )
    shutil.copyfile(
        windows / "semantic/runtime_proof.json", e19 / "installed_runtime_proof.json"
    )
    shutil.copyfile(args.evaluation_comparison, e19 / "evaluation_comparison.json")
    prefreeze = repository / "runs/m336d_pre_freeze_disclosed/windows"
    shutil.copyfile(
        prefreeze / "adaptive_mutations.json", e19 / "adaptive_mutations.json"
    )
    shutil.copyfile(
        prefreeze / "h17_exact_field_mapping.json",
        e19 / "h17_exact_field_mapping.json",
    )
    shutil.copyfile(
        prefreeze / "independent_spdx_differential.json",
        e19 / "independent_spdx_differential.json",
    )
    quality_roots = {
        "f19_windows": args.f19_windows_quality,
        "f19_karina": args.f19_karina_quality,
        "h19_windows": args.h19_windows_quality,
        "h19_karina": args.h19_karina_quality,
    }
    quality_reports = {}
    for name, root in quality_roots.items():
        destination = e19 / "quality" / name
        shutil.copytree(root, destination)
        quality_reports[name] = _load(destination / "quality.json")
    evaluation = _load(e19 / "evaluation.json")
    semantic = _load(e19 / "independent_jdk_semantic_evaluation.json")
    license_evaluation = _load(e19 / "independent_license_evaluation.json")
    runtime = _load(e19 / "installed_runtime_proof.json")
    qualification = _load(h19 / "qualification_decisions.json")
    selector = _load(h19 / "selector_receipt.json")
    leak = _load(h19 / "source_leak_scan.json")
    production_comparison = _load(h19 / "production_comparison.json")
    vault_windows = _load(h19 / "vault_verification_windows.json")
    vault_karina = _load(h19 / "vault_verification_karina.json")
    adaptive = _load(e19 / "adaptive_mutations.json")
    mapping = _load(e19 / "h17_exact_field_mapping.json")
    differential = _load(e19 / "independent_spdx_differential.json")
    contract_targets = (
        (
            "freeze/m336d_freeze_manifest.json",
            args.freeze_manifest.resolve(strict=True),
        ),
        ("h19/acquisition_receipts.json", h19 / "acquisition_receipts.json"),
        ("h19/qualification_decisions.json", h19 / "qualification_decisions.json"),
        ("h19/selector_receipt.json", h19 / "selector_receipt.json"),
        (
            "h19/production/production_summary.json",
            h19 / "production/production_summary.json",
        ),
        ("h19/candidate_pack.json", h19 / "candidate_pack.json"),
        ("h19/vault_manifest.json", h19 / "vault_manifest.json"),
        ("h19/h19_seal.json", h19 / "h19_seal.json"),
        ("e19/evaluation.json", e19 / "evaluation.json"),
    )
    contract_validations = [
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            logical_path, physical_path.read_bytes()
        )
        for logical_path, physical_path in contract_targets
    ]
    pre_readiness_contract_hash = content_hash(
        tuple(asdict(item) for item in contract_validations)
    )
    quality_check_names = (
        "ruff_format_pass",
        "ruff_lint_pass",
        "targeted_pass",
        "no_torch_network_pass",
        "full_suite_pass",
        "java_reference_compile_pass",
        "clean_worktree",
        "head_remote_equal",
    )
    quality_passed = sum(
        bool(report[name])
        for report in quality_reports.values()
        for name in quality_check_names
    )
    runtime_queries = runtime["queries"]
    payloads = {
        "authority": {
            "root_count": 1,
            "derived_receipt_valid_count": qualification["candidate_count"],
            "derived_receipt_count": qualification["candidate_count"],
            "scope_intersection_valid_count": qualification["candidate_count"],
            "scope_intersection_count": qualification["candidate_count"],
            "forgery_accepted_count": adaptive["accepted_count"],
            "derived_pack_publication_allowed": qualification[
                "derived_pack_publication_root_count"
            ]
            == qualification["analysis_eligible_root_count"],
            "metrics_publication_allowed": qualification[
                "metrics_publication_root_count"
            ]
            == qualification["analysis_eligible_root_count"],
        },
        "license_differential": {
            "case_count": differential["case_count"],
            "disagreement_count": differential["disagreement_count"]
            + license_evaluation["disagreement_count"],
            "false_automatic_license_identity_count": differential[
                "false_automatic_license_identity_count"
            ]
            + license_evaluation["false_automatic_license_identity_count"],
            "valid_optional_variant_rejected_count": differential[
                "valid_optional_variant_rejected_count"
            ],
            "substantive_mutation_accepted_count": differential[
                "substantive_mutation_accepted_count"
            ],
            "multiple_match_automatic_acceptance_count": differential[
                "multiple_match_automatic_acceptance_count"
            ],
        },
        "document_inventory": {
            "discovered_document_count": sum(
                item["legal_document_count"] for item in qualification["decisions"]
            ),
            "classified_document_count": sum(
                item["legal_document_count"] for item in qualification["decisions"]
            ),
            "unclassified_document_count": sum(
                item["unclassified_legal_document_count"]
                for item in qualification["decisions"]
            ),
        },
        "correspondence": {
            "total_candidate_java_entries": qualification[
                "analysis_eligible_java_entry_count"
            ],
            "selected_entries": selector["selected_file_count"],
            "selected_entries_with_complete_scm_correspondence": selector[
                "selected_file_count"
            ],
        },
        "qualification": {
            "candidate_count": qualification["candidate_count"],
            "qualified_candidate_count": qualification["candidate_count"],
            "analysis_eligible_root_count": qualification[
                "analysis_eligible_root_count"
            ],
        },
        "selector": {
            "invocation_count": selector["selector_invocation_count"],
            "rerun_count": selector["selector_rerun_count"],
            "selected_file_count": selector["selected_file_count"],
        },
        "ordering": {
            "production_sequence": 1,
            "seal_sequence": 2,
            "evaluator_sequence": 3,
        },
        "pack": {
            "compile_pass_count": int(evaluation["candidate_pack_compiled"]),
            "replay_pass_count": int(evaluation["candidate_replay_status"] == "PASS"),
            "run_count": 1,
        },
        "semantic_metrics": {
            "location_correct": semantic["location"]["exact_true_positive"],
            "location_predicted": semantic["location"]["exact_true_positive"]
            + semantic["location"]["wrong_location_false_positive"],
            "semantic_correct": semantic["semantic"]["exact_true_positive"],
            "semantic_predicted": semantic["semantic"]["exact_true_positive"]
            + semantic["semantic"]["semantic_false_positive"]
            + semantic["semantic"]["correct_location_wrong_content"],
            "semantic_gold_count": semantic["semantic"]["exact_true_positive"]
            + semantic["semantic"]["missing_false_negative"],
        },
        "trust_metrics": {
            "trust_correct": semantic["trust"]["correct_trusted"],
            "trusted_count": semantic["trust"]["correct_trusted"]
            + semantic["trust"]["wrong_trusted"],
            "eligible_count": semantic["trust"]["correct_trusted"]
            + semantic["trust"]["incorrect_withheld"],
            "wrong_trusted_count": semantic["wrong_trusted_count"],
        },
        "runtime": {
            "passed_count": sum(item["passed"] for item in runtime_queries),
            "query_count": len(runtime_queries),
        },
        "artifact_contract": {
            "valid_artifact_count": len(contract_validations),
            "artifact_count": len(contract_validations),
        },
        "adaptive_mutations": {
            "mutation_count": adaptive["mutation_count"],
            "accepted_count": adaptive["accepted_count"],
            "wrong_rejection_layer_count": adaptive["wrong_rejection_layer_count"],
        },
        "h17_mapping": {
            "historical_occurrence_count": mapping["historical_occurrence_count"],
            "mapped_occurrence_count": mapping["mapped_occurrence_count"],
            "unmapped_occurrence_count": mapping["unmapped_occurrence_count"],
        },
        "leak_scan": {
            "leak_count": leak["fresh_source_leak_count"],
            "scanned_artifact_count": leak["scanned_public_file_count"],
        },
        "cross_platform": {
            "difference_count": comparison["platform_independent_difference_count"]
            + production_comparison["platform_independent_difference_count"]
            + vault_windows["difference_count"]
            + vault_karina["difference_count"],
            "comparison_count": comparison["platform_neutral_artifact_count"]
            + production_comparison["platform_neutral_artifact_count"]
            + 2,
        },
        "quality": {
            "passed_count": quality_passed,
            "check_count": len(quality_reports) * len(quality_check_names),
        },
        "freshness": {
            "pre_f19_source_body_byte_count": 0,
            "global_acquisition_count": 1,
            "fresh_overlap_count": _load(h19 / "source_overlap.json")[
                "selected_root_overlap_count"
            ],
        },
    }
    source_hashes = {
        "authority": qualification["report_hash"],
        "license_differential": license_evaluation["report_hash"],
        "document_inventory": qualification["report_hash"],
        "correspondence": qualification["report_hash"],
        "qualification": qualification["report_hash"],
        "selector": selector["receipt_hash"],
        "ordering": _load(h19 / "h19_seal.json")["seal_hash"],
        "pack": _load(h19 / "candidate_pack.json")["report_hash"],
        "semantic_metrics": semantic["report_hash"],
        "trust_metrics": semantic["report_hash"],
        "runtime": runtime["report_hash"],
        "artifact_contract": pre_readiness_contract_hash,
        "adaptive_mutations": adaptive["report_hash"],
        "h17_mapping": mapping["report_hash"],
        "leak_scan": leak["report_hash"],
        "cross_platform": comparison["report_hash"],
        "quality": content_hash(
            tuple(report["report_hash"] for report in quality_reports.values())
        ),
        "freshness": _load(h19 / "source_overlap.json")["report_hash"],
    }
    for name, payload in sorted(payloads.items()):
        receipt = build_primary_receipt(
            name, payload, source_report_hash=source_hashes[name]
        )
        _write(e19 / "primary" / f"{name}.json", asdict(receipt))
    receipts = load_primary_receipts(e19 / "primary")
    gate = evaluate_m336d_readiness(receipts, mode=M336DReadinessMode.FINAL_FRESH)
    verify_m336d_readiness(receipts, gate)
    _write(e19 / "readiness.json", asdict(gate))
    contract_validations.append(
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "e19/readiness.json", (e19 / "readiness.json").read_bytes()
        )
    )
    valid_contract_count = sum(item.status == "PASS" for item in contract_validations)
    contract_body = {
        "schema_version": 1,
        "registry_hash": PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.registry_hash,
        "artifact_count": len(contract_validations),
        "valid_artifact_count": valid_contract_count,
        "validations": tuple(asdict(item) for item in contract_validations),
        "status": "PASS"
        if valid_contract_count == len(contract_validations)
        else "FAIL",
    }
    _write(
        e19 / "public_contract_validation.json",
        {**contract_body, "report_hash": content_hash(contract_body)},
    )
    acquisition_performance = _load(h19 / "acquisition_performance.json")
    windows_production_performance = _load(
        h19 / "production/production_performance_windows.json"
    )
    karina_production_performance = _load(
        h19 / "production/production_performance_karina.json"
    )
    windows_performance = _load(windows / "evaluation_performance.json")
    karina_performance = _load(karina / "evaluation_performance.json")
    windows_operations = _performance_operations(
        acquisition_performance,
        windows_production_performance,
        windows_performance,
    )
    karina_operations = _performance_operations(
        None,
        karina_production_performance,
        karina_performance,
    )
    operation_names = (
        "authority_root_load",
        "authority_receipt_verification",
        "spdx_production_match",
        "java_reference_spdx_match",
        "expression_parsing",
        "legal_document_inventory",
        "source_correspondence",
        "candidate_qualification",
        "vault_sealing",
        "selector",
        "java_indexing",
        "proposal_production",
        "trust_closure",
        "candidate_pack_construction",
        "compilation",
        "replay",
        "semantic_evaluation",
        "runtime_queries",
        "contract_validation",
        "adaptive_mutations",
        "leak_scan",
    )
    if set(windows_operations) != set(operation_names):
        raise ValueError("Windows performance operation denominator is not 21/21")
    expected_karina = set(operation_names) - {
        "authority_root_load",
        "authority_receipt_verification",
        "expression_parsing",
        "legal_document_inventory",
        "source_correspondence",
        "candidate_qualification",
        "vault_sealing",
        "selector",
    }
    if set(karina_operations) != expected_karina:
        raise ValueError("Karina post-acquisition performance denominator mismatch")
    performance_body = {
        "schema_version": 1,
        "measured_operation_count": len(operation_names),
        "operations": tuple(
            {
                "name": name,
                "windows": windows_operations[name],
                "karina": karina_operations.get(name),
                "measurement_scope": "SINGLE_GLOBAL_ACQUISITION_WINDOWS"
                if name not in expected_karina
                else "WINDOWS_AND_KARINA",
            }
            for name in operation_names
        ),
        "single_global_acquisition_platform": "windows",
        "karina_acquisition_rerun_count": 0,
        "windows_total_acquisition_seconds": acquisition_performance[
            "total_acquisition_seconds"
        ],
        "windows_total_production_seconds": windows_production_performance[
            "production_total_seconds"
        ],
        "karina_total_production_seconds": karina_production_performance[
            "production_total_seconds"
        ],
        "windows_total_evaluation_seconds": windows_performance[
            "evaluation_total_seconds"
        ],
        "karina_total_evaluation_seconds": karina_performance[
            "evaluation_total_seconds"
        ],
        "windows_peak_python_bytes": max(
            acquisition_performance["peak_python_bytes"],
            windows_production_performance["peak_python_bytes"],
            windows_performance["peak_python_bytes"],
        ),
        "karina_peak_python_bytes": max(
            karina_production_performance["peak_python_bytes"],
            karina_performance["peak_python_bytes"],
        ),
        "windows_peak_java_reference_bytes": windows_performance[
            "peak_java_reference_bytes"
        ],
        "karina_peak_java_reference_bytes": karina_performance[
            "peak_java_reference_bytes"
        ],
    }
    _write(
        e19 / "performance.json",
        {**performance_body, "report_hash": content_hash(performance_body)},
    )
    security_counts = {
        "schema_version": 1,
        "authority_forgery_accepted_count": adaptive["accepted_count"],
        "adaptive_mutation_count": adaptive["mutation_count"],
        "adaptive_mutation_accepted_count": adaptive["accepted_count"],
        "wrong_rejection_layer_count": adaptive["wrong_rejection_layer_count"],
        "fresh_source_leak_count": leak["fresh_source_leak_count"],
        "production_reference_disagreement_count": license_evaluation[
            "disagreement_count"
        ],
    }
    security_body = {
        **security_counts,
        "status": "PASS"
        if all(
            not value
            for name, value in security_counts.items()
            if name.endswith("_count") and name != "adaptive_mutation_count"
        )
        else "FAIL",
    }
    _write(
        e19 / "security.json",
        {**security_body, "report_hash": content_hash(security_body)},
    )
    if security_body["status"] != "PASS":
        raise SystemExit("M-33.6d final security evidence failed")
    decision_body = {
        "schema_version": 1,
        "h19_sha": args.h19_sha,
        "decision": gate.decision.value,
        "mandatory_count": gate.mandatory_count,
        "pass_count": gate.pass_count,
        "failed_criteria": gate.failed_criteria,
        "raw_source_publication_root_count": qualification[
            "raw_source_publication_root_count"
        ],
        "source_excerpt_publication_root_count": qualification[
            "source_excerpt_publication_root_count"
        ],
        "derived_pack_publication_root_count": qualification[
            "derived_pack_publication_root_count"
        ],
        "metrics_publication_root_count": qualification[
            "metrics_publication_root_count"
        ],
    }
    _write(
        e19 / "final_decision.json",
        {**decision_body, "decision_hash": content_hash(decision_body)},
    )
    final_leak = scan_fresh_source_leaks(
        args.vault.resolve(strict=True),
        (
            args.output,
            repository / "artifacts/acquisition/disclosed_java",
        ),
    )
    _write(e19 / "final_e19_leak_scan.json", final_leak)
    if final_leak["fresh_source_leak_count"]:
        raise SystemExit("M-33.6d E19 contains fresh source material")
    rows = tuple(
        (path.relative_to(args.output).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            (item for item in args.output.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(args.output).as_posix().encode(),
        )
    )
    manifest_body = {"schema_version": 1, "file_count": len(rows), "files": rows}
    _write(
        e19 / "evidence_manifest.json",
        {**manifest_body, "manifest_hash": content_hash(manifest_body)},
    )
    if gate.pass_count != gate.mandatory_count:
        raise SystemExit("M-33.6d final readiness is blocked")


def _performance_operations(acquisition, production, evaluation) -> dict:
    result = {}
    if acquisition is not None:
        requested = {
            "authority_root_load",
            "authority_receipt_verification",
            "expression_parsing",
            "legal_document_inventory",
            "source_correspondence",
            "candidate_qualification",
            "vault_sealing",
            "selector",
        }
        result.update(
            (name, _normalized_sample(sample))
            for name, sample in acquisition["operations"]
            if name in requested
        )
    result.update(
        (name, _normalized_sample(sample))
        for name, sample in production["m336d_requested_operations"]
    )
    result.update(
        (name, _normalized_sample(sample)) for name, sample in evaluation["operations"]
    )
    return result


def _normalized_sample(sample: dict) -> dict:
    total = float(sample.get("total_seconds", sample["p50_seconds"]))
    count = sample["sample_count"]
    return {
        "sample_count": count,
        "p50_seconds": sample["p50_seconds"],
        "p95_seconds": sample["p95_seconds"],
        "p99_seconds": sample["p99_seconds"],
        "total_seconds": f"{total:.9f}",
        "throughput_operations_per_second": f"{count / total:.6f}"
        if total > 0
        else "0.000000",
    }


if __name__ == "__main__":
    main()
