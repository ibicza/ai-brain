"""Assemble the exact-R20 disclosed full-path qualification decision."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


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
    parser.add_argument("--r20-sha", required=True)
    parser.add_argument("--windows-preflight", type=Path, required=True)
    parser.add_argument("--karina-selection-verification", type=Path, required=True)
    parser.add_argument("--vault-comparison", type=Path, required=True)
    parser.add_argument(
        "--registry-simulation", type=Path, action="append", required=True
    )
    parser.add_argument("--windows-production", type=Path, required=True)
    parser.add_argument("--karina-production", type=Path, required=True)
    parser.add_argument("--production-comparison", type=Path, required=True)
    parser.add_argument("--windows-evaluation", type=Path, required=True)
    parser.add_argument("--karina-evaluation", type=Path, required=True)
    parser.add_argument("--evaluation-comparison", type=Path, required=True)
    parser.add_argument("--evaluation-completion", type=Path, required=True)
    parser.add_argument("--contract-gate", type=Path, required=True)
    parser.add_argument("--leak-report", type=Path, required=True)
    parser.add_argument("--security", type=Path, required=True)
    parser.add_argument("--performance", type=Path, required=True)
    parser.add_argument("--quality", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    if (
        _git(repository, "rev-parse", "HEAD^{commit}") != args.r20_sha
        or len(args.r20_sha) != 40
        or _git(repository, "status", "--porcelain=v1")
    ):
        raise ValueError("Q20 assembly requires a clean exact-R20 worktree")
    if args.output.exists():
        raise FileExistsError("fresh Q20 summary already exists")

    preflight_root = args.windows_preflight.resolve(strict=True)
    preflight = _load(preflight_root / "preflight_summary.json")
    selector = _load(preflight_root / "selector_receipt.json")
    census = _load(preflight_root / "selectability_census.json")
    proof = _load(preflight_root / "selector_feasibility.json")
    protocol = _load(preflight_root / "protocol_ledger_receipt.json")
    karina_verify = _load(
        args.karina_selection_verification.resolve(strict=True)
        / "selector_verify_only_receipt.json"
    )
    vault = _load(args.vault_comparison.resolve(strict=True))
    simulations = tuple(
        _load(path.resolve(strict=True) / "verification.json")
        for path in args.registry_simulation
    )
    windows_root = args.windows_production.resolve(strict=True)
    karina_root = args.karina_production.resolve(strict=True)
    windows_production = _load(windows_root / "production_summary.json")
    karina_production = _load(karina_root / "production_summary.json")
    production_counts = _load(windows_root / "production_counts.json")
    production_comparison = _load(args.production_comparison.resolve(strict=True))
    windows_evaluation = _load(args.windows_evaluation.resolve(strict=True))
    karina_evaluation = _load(args.karina_evaluation.resolve(strict=True))
    evaluation_comparison = _load(args.evaluation_comparison.resolve(strict=True))
    completion = _load(args.evaluation_completion.resolve(strict=True))
    contract = _load(args.contract_gate.resolve(strict=True))
    leak = _load(args.leak_report.resolve(strict=True))
    security = _load(args.security.resolve(strict=True))
    performance = _load(args.performance.resolve(strict=True))
    qualities = tuple(_load(path.resolve(strict=True)) for path in args.quality)
    neutral_fields = (
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
    criteria = (
        ("preflight_pass", preflight["status"] == "PASS"),
        ("selectable_roots", census["selectable_root_count"] >= 3),
        ("selected_files", selector["selected_file_count"] == 180),
        ("selected_roots", selector["selected_root_count"] >= 3),
        ("root_cap", selector["maximum_one_root_count"] <= 63),
        ("balanced_capacity", proof["balanced_capacity"] >= 180),
        ("feasibility", proof["hard_requirements_satisfied"] is True),
        ("selector_once", selector["selector_invocation_count"] == 1),
        ("selector_rerun_zero", selector["selector_rerun_count"] == 0),
        (
            "karina_verify_only",
            karina_verify["selector_invocation_count_on_verifier"] == 0,
        ),
        ("vault_physical_equal", vault["physical_difference_count"] == 0),
        ("vault_manifest_equal", vault["canonical_manifest_difference_count"] == 0),
        ("vault_tree_equal", vault["portable_tree_hash_difference_count"] == 0),
        (
            "registry_current_thirty",
            all(item["previous_entry_count"] == 30 for item in simulations),
        ),
        (
            "registry_append_31_54_78",
            {item["resulting_entry_count"] for item in simulations} == {31, 54, 78},
        ),
        (
            "registry_original_six",
            all(item["original_six_entries_preserved"] for item in simulations),
        ),
        ("windows_production", windows_production["status"] == "PASS"),
        ("karina_production", karina_production["status"] == "PASS"),
        (
            "production_equal",
            production_comparison["platform_independent_difference_count"] == 0,
        ),
        (
            "pack_integrity",
            production_counts["post_trust_pack_failures"] == 0
            and windows_production["candidate_replay_status"] == "PASS",
        ),
        (
            "production_oracle_free",
            windows_production["production_evaluator_dependency_count"] == 0
            and windows_production["production_golden_read_count"] == 0,
        ),
        (
            "ledger_once",
            protocol["global_acquisition_count"] == 1
            and protocol["selector_invocation_count"] == 1,
        ),
        ("windows_evaluation", windows_evaluation["status"] == "PASS"),
        ("karina_evaluation", karina_evaluation["status"] == "PASS"),
        (
            "evaluation_fields_equal",
            all(
                windows_evaluation[name] == karina_evaluation[name]
                for name in neutral_fields
            ),
        ),
        (
            "evaluation_artifacts_equal",
            evaluation_comparison["platform_independent_difference_count"] == 0,
        ),
        (
            "spdx_agreement",
            windows_evaluation["production_reference_license_agreement"] == "1.000000",
        ),
        (
            "semantic_thresholds",
            windows_evaluation["location_precision"] == "1.000000"
            and windows_evaluation["location_recall"] >= "0.950000"
            and windows_evaluation["semantic_precision"] == "1.000000"
            and windows_evaluation["semantic_recall"] >= "0.950000",
        ),
        (
            "trust_thresholds",
            windows_evaluation["trust_precision"] == "1.000000"
            and windows_evaluation["trust_coverage"] >= "0.850000"
            and windows_evaluation["wrong_trusted_count"] == 0,
        ),
        (
            "runtime",
            windows_evaluation["runtime_status"] == "PASS"
            and windows_evaluation["runtime_network_access_count"] == 0,
        ),
        (
            "evaluation_completed",
            completion["status"] == "PASS"
            and completion["protocol_ledger_receipt"]["final_event_type"]
            == "EVALUATION_COMPLETED",
        ),
        (
            "contracts",
            contract["status"] == "PASS"
            and contract["uncontracted_produced_artifact_count"] == 0,
        ),
        ("leaks", leak["fresh_source_leak_count"] == 0),
        ("security", security["status"] == "PASS"),
        ("performance", performance["status"] == "PASS"),
        (
            "quality",
            len(qualities) >= 2 and all(_quality_passed(item) for item in qualities),
        ),
    )
    passed = sum(value for _name, value in criteria)
    evidence_inputs = tuple(
        sorted(
            (str(path), bytes_hash(path.read_bytes()))
            for path in (
                args.vault_comparison,
                args.production_comparison,
                args.evaluation_comparison,
                args.evaluation_completion,
                args.contract_gate,
                args.leak_report,
                args.security,
                args.performance,
                *args.quality,
            )
        )
    )
    body = {
        "schema_version": 2,
        "r20_sha": args.r20_sha,
        "criterion_count": len(criteria),
        "passed_criterion_count": passed,
        "failed_criterion_count": len(criteria) - passed,
        "criteria": criteria,
        "evidence_input_manifest_hash": content_hash(evidence_inputs),
        "status": "PASS" if passed == len(criteria) else "FAIL",
    }
    _write(args.output, {**body, "report_hash": content_hash(body)})
    if body["status"] != "PASS":
        raise SystemExit("M-33.6e exact-R20 disclosed qualification is BLOCKED")


if __name__ == "__main__":
    main()
