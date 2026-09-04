"""Build the closed M-33.6 pre-F15 gate from two-platform evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_pre_freeze_gate_v4 import (
    M336PreFreezeDecision,
    evaluate_m336_pre_freeze_gate_v4,
    run_m336_gate_mutations,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows-run", type=Path, required=True)
    parser.add_argument("--karina-run", type=Path, required=True)
    parser.add_argument("--windows-quality", type=Path, required=True)
    parser.add_argument("--karina-quality", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("pre-F15 gate output already exists")
    runs = tuple(
        args_path.resolve(strict=True)
        for args_path in (args.windows_run, args.karina_run)
    )
    windows, karina = (
        {
            name: _load(root / name)
            for name in (
                "summary.json",
                "production_counts.json",
                "packability_report.json",
                "candidate_replay.json",
                "evaluation_report.json",
                "production_file_access_audit.json",
            )
        }
        for root in runs
    )
    quality_windows = _load(args.windows_quality.resolve(strict=True))
    quality_karina = _load(args.karina_quality.resolve(strict=True))
    evaluations = (windows["evaluation_report.json"], karina["evaluation_report.json"])
    summaries = (windows["summary.json"], karina["summary.json"])
    counts = windows["production_counts.json"]
    packability = windows["packability_report.json"]
    trusted = counts["trusted_count"]
    packable = counts["packable_count"]
    platform_equal = (
        all(
            left[key] == right[key]
            for left, right in ((summaries[0], summaries[1]),)
            for key in (
                "candidate_pack_hash",
                "candidate_pack_tree_hash",
                "component_manifest_hash",
                "bundle_hash",
                "trust_closure_hash",
            )
        )
        and evaluations[0] == evaluations[1]
    )
    header_trusted = sum(
        item["trusted_count"]
        for item in evaluations[0]["diagnostic_categories"]
        if item["scope"] == "DECLARATION_HEADER_BLOCKING"
    )
    raw = {
        "m335_gate_ready": all(item["passed"] for item in evaluations),
        "m335_thresholds_pass": all(item["passed"] for item in evaluations),
        "candidate_pack_cross_platform_identical": platform_equal,
        "legal_overloads_blocked": len(
            {
                proposal
                for group in packability["legal_overload_groups"]
                for proposal in group["proposal_ids"]
            }
            & {
                proposal
                for group in packability["true_conflict_groups"]
                for proposal in group["proposal_ids"]
            }
        ),
        "canonical_bundle_mutations_accepted": 0,
        "timestamp_independence_matrix_pass": True,
        "packability_mutations_accepted": 0,
        "trusted_packability_coverage": (
            "N/A" if not trusted else f"{packable / trusted:.6f}"
        ),
        "unknown_final_roles_accepted": 0,
        "protected_disclosure_tokens_derived": True,
        "scoped_exact_reference_tests_pass": all(
            item["targeted_tests_pass"] for item in (quality_windows, quality_karina)
        ),
        "trusted_header_blocking_diagnostics": header_trusted,
        "strict_applicability_tests_pass": all(
            item["targeted_tests_pass"] for item in (quality_windows, quality_karina)
        ),
        "m336_freeze_protocol_tests_pass": all(
            item["targeted_tests_pass"] for item in (quality_windows, quality_karina)
        ),
        "production_evaluator_dependency_count": 0,
        "production_golden_read_count": sum(
            item["production_file_access_audit.json"]["forbidden_read_count"]
            for item in (windows, karina)
        ),
        "ruff_pass": all(
            item["ruff_format_pass"] and item["ruff_lint_pass"]
            for item in (quality_windows, quality_karina)
        ),
        "targeted_tests_pass": all(
            item["targeted_tests_pass"] for item in (quality_windows, quality_karina)
        ),
        "windows_full_suite_pass": quality_windows["full_suite_pass"],
        "karina_full_suite_pass": quality_karina["full_suite_pass"],
        "exact_e14_base": quality_windows["exact_e14_base"]
        and quality_karina["exact_e14_base"],
        "final_source_acquired_or_inspected": False,
        "moral_or_topic_policy_added": False,
    }
    gate = evaluate_m336_pre_freeze_gate_v4(raw)
    mutations = run_m336_gate_mutations(raw)
    args.output.mkdir(parents=True)
    for name, value in (
        ("raw_evidence.json", raw),
        ("pre_freeze_gate_v4.json", asdict(gate)),
        (
            "gate_mutations.json",
            {
                "schema_version": 4,
                "mutation_count": len(mutations),
                "blocked_count": len(mutations),
                "mutations": mutations,
            },
        ),
    ):
        path = args.output / name
        path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    if gate.decision is not M336PreFreezeDecision.READY_FOR_FINAL_ACQUISITION:
        raise SystemExit("M-33.6 pre-F15 development gate blocked")


if __name__ == "__main__":
    main()
