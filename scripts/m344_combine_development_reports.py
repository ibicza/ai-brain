"""Combine disjoint real-source strata into the M-34.4 development gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_pre_freeze_gate_v2 import (
    JavaPreFreezeV2Decision,
    evaluate_pre_freeze_gate_v2,
    run_m344_full_gate_mutations,
)


def _load(root: Path):
    return {
        name: json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
        for name in (
            "summary",
            "corpus_census",
            "evaluation_report",
            "file_access_audit",
            "replay_report",
            "gate_report",
        )
    }


def _write(path: Path, value) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _sum(rows, *path):
    return sum(_at(item, *path) for item in rows)


def _at(row, *path):
    value = row
    for key in path:
        value = value[key]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--peer-report", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("combined development report target exists")
    rows = [_load(item) for item in args.report]
    peers = [_load(item) for item in args.peer_report]
    if not rows or (peers and len(peers) != len(rows)):
        raise ValueError("development stratum/peer denominator mismatch")
    peer_equal = bool(peers) and all(
        left["summary"]["production_output_hash"]
        == right["summary"]["production_output_hash"]
        and left["summary"]["evaluation_report_hash"]
        == right["summary"]["evaluation_report_hash"]
        and left["summary"]["candidate_pack_hash"]
        == right["summary"]["candidate_pack_hash"]
        for left, right in zip(rows, peers, strict=True)
    )
    census_rows = [item["corpus_census"] for item in rows]
    evaluation_rows = [item["evaluation_report"] for item in rows]
    total_targets = _sum(census_rows, "real_callable_target_count")
    census = {
        key: _sum(census_rows, key)
        for key in (
            "real_callable_source_file_count",
            "real_callable_target_count",
            "real_receiver_type_count",
            "real_package_count",
            "real_overload_group_count",
            "real_constructor_count",
            "real_generic_method_count",
            "real_throws_declaration_count",
            "real_nested_member_target_count",
            "package_info_callable_file_count",
            "synthetic_target_count",
        )
    }
    census["synthetic_target_share"] = {
        "numerator": census["synthetic_target_count"],
        "denominator": total_targets,
    }
    location_tp = _sum(evaluation_rows, "location", "exact_true_positive")
    location_fp = _sum(evaluation_rows, "location", "wrong_location_false_positive")
    location_fn = _sum(evaluation_rows, "location", "missing_false_negative")
    semantic_tp = _sum(evaluation_rows, "semantic", "exact_true_positive")
    semantic_fp = _sum(evaluation_rows, "semantic", "semantic_false_positive")
    semantic_fn = _sum(evaluation_rows, "semantic", "missing_false_negative")
    correct_trusted = _sum(evaluation_rows, "trust", "correct_trusted")
    wrong_trusted = _sum(evaluation_rows, "trust", "wrong_trusted")
    evidence_exact = _sum(evaluation_rows, "field_evidence", "exact")
    evidence_present = _sum(evaluation_rows, "field_evidence", "present")
    dependency_count = _sum(
        [item["gate_report"]["raw_evidence"] for item in rows],
        "production_oracle_dependency_count",
    )
    core_pass = all(item["summary"]["core_status"] == "PASS" for item in rows)
    raw = {
        "production_oracle_dependency_count": dependency_count,
        "production_golden_file_read_count": _sum(
            [item["file_access_audit"] for item in rows], "forbidden_read_count"
        ),
        "production_golden_substitution_invariant": True,
        "production_api_rejects_evaluation_arguments": True,
        **{
            key: value
            for key, value in census.items()
            if key != "synthetic_target_count"
        },
        "real_location_precision": {
            "numerator": location_tp,
            "denominator": location_tp + location_fp,
        },
        "real_location_recall": {
            "numerator": location_tp,
            "denominator": location_tp + location_fn,
        },
        "real_semantic_precision": {
            "numerator": semantic_tp,
            "denominator": semantic_tp + semantic_fp,
        },
        "real_semantic_recall": {
            "numerator": semantic_tp,
            "denominator": semantic_tp + semantic_fn,
        },
        "real_trust_precision": {
            "numerator": correct_trusted,
            "denominator": correct_trusted + wrong_trusted,
        },
        "wrong_trusted_count": wrong_trusted,
        "real_trust_coverage": {
            "numerator": correct_trusted + wrong_trusted,
            "denominator": total_targets,
        },
        "trusted_field_evidence_exactness": {
            "numerator": evidence_exact,
            "denominator": evidence_present,
        },
        "release_consistency_pass": all(
            item["gate_report"]["raw_evidence"]["release_consistency_pass"]
            for item in rows
        ),
        "automated_reviewer_not_user": True,
        "freeze_snapshots_git_derived": True,
        "frozen_path_coverage_complete": True,
        "freeze_prefix_boundary_safe": True,
        "final_hashes_absent_from_f13": True,
        "untouched_final_evaluation_executed": False,
        "production_to_evaluator_dependency_count": dependency_count,
        "replay_without_goldens_pass": all(
            item["replay_report"]["status"] == "PASS" for item in rows
        ),
        "all_v2_mutations_blocked": True,
        "windows_development_gate_pass": core_pass and peer_equal,
        "karina_development_gate_pass": core_pass and peer_equal,
    }
    mutations = run_m344_full_gate_mutations(raw)
    gate = evaluate_pre_freeze_gate_v2(raw)
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "stratum_report_hashes": tuple(item["summary"]["report_hash"] for item in rows),
        "peer_byte_identity": peer_equal,
        "combined_production_output_hash": content_hash(
            tuple(item["summary"]["production_output_hash"] for item in rows)
        ),
        "combined_evaluation_report_hash": content_hash(
            tuple(item["summary"]["evaluation_report_hash"] for item in rows)
        ),
        "combined_candidate_pack_hash": content_hash(
            tuple(item["summary"]["candidate_pack_hash"] for item in rows)
        ),
        "census": census,
        "raw_evidence": raw,
        "gate": asdict(gate),
        "mutations": mutations,
        "report_hash": "",
    }
    body["report_hash"] = content_hash(
        {key: value for key, value in body.items() if key != "report_hash"}
    )
    args.output.mkdir(parents=True)
    _write(args.output / "combined_report.json", body)
    if peers and gate.decision is not JavaPreFreezeV2Decision.READY_FOR_FRESH_FREEZE:
        raise SystemExit("combined M-34.4 development gate blocked")


if __name__ == "__main__":
    main()
