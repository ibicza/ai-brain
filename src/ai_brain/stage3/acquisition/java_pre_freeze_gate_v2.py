"""Derived M-34.4 gate for an oracle-free real-callable Java freeze."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash


class JavaPreFreezeV2Decision(StrEnum):
    READY_FOR_FRESH_FREEZE = "READY_FOR_FRESH_FREEZE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class JavaPreFreezeV2Criterion:
    criterion_id: str
    evidence_key: str
    measured_value: str
    threshold: str
    status: str
    evidence_hash: str


@dataclass(frozen=True)
class JavaPreFreezeV2Report:
    schema_version: int
    criteria: tuple[JavaPreFreezeV2Criterion, ...]
    mandatory_count: int
    pass_count: int
    fail_count: int
    decision: JavaPreFreezeV2Decision
    raw_evidence_hash: str
    report_hash: str


M344_PRE_FREEZE_V2_SPECS = (
    (
        "production.oracle_dependencies",
        "production_oracle_dependency_count",
        "MAX",
        "0",
    ),
    ("production.golden_reads", "production_golden_file_read_count", "MAX", "0"),
    (
        "production.golden_invariant",
        "production_golden_substitution_invariant",
        "BOOL",
        "true",
    ),
    (
        "production.api_rejects_goldens",
        "production_api_rejects_evaluation_arguments",
        "BOOL",
        "true",
    ),
    ("corpus.real_callable_files", "real_callable_source_file_count", "MIN", "40"),
    ("corpus.real_callables", "real_callable_target_count", "MIN", "1000"),
    ("corpus.receiver_types", "real_receiver_type_count", "MIN", "100"),
    ("corpus.packages", "real_package_count", "MIN", "10"),
    ("corpus.overloads", "real_overload_group_count", "MIN", "75"),
    ("corpus.constructors", "real_constructor_count", "MIN", "40"),
    ("corpus.generics", "real_generic_method_count", "MIN", "75"),
    ("corpus.throws", "real_throws_declaration_count", "MIN", "75"),
    ("corpus.nested", "real_nested_member_target_count", "MIN", "20"),
    ("corpus.package_info_excluded", "package_info_callable_file_count", "MAX", "0"),
    ("corpus.synthetic_share", "synthetic_target_share", "MAX", "0.500000"),
    ("location.precision", "real_location_precision", "MIN", "1.000000"),
    ("location.recall", "real_location_recall", "MIN", "0.950000"),
    ("semantic.precision", "real_semantic_precision", "MIN", "1.000000"),
    ("semantic.recall", "real_semantic_recall", "MIN", "0.950000"),
    ("trust.precision", "real_trust_precision", "MIN", "1.000000"),
    ("trust.wrong", "wrong_trusted_count", "MAX", "0"),
    ("trust.coverage", "real_trust_coverage", "MIN", "0.800000"),
    ("evidence.exactness", "trusted_field_evidence_exactness", "MIN", "1.000000"),
    ("release.consistency", "release_consistency_pass", "BOOL", "true"),
    ("review.identity", "automated_reviewer_not_user", "BOOL", "true"),
    ("freeze.git_derived", "freeze_snapshots_git_derived", "BOOL", "true"),
    ("freeze.full_scope", "frozen_path_coverage_complete", "BOOL", "true"),
    ("freeze.prefix_safe", "freeze_prefix_boundary_safe", "BOOL", "true"),
    ("freeze.no_final_hash", "final_hashes_absent_from_f13", "BOOL", "true"),
    ("evaluation.untouched", "untouched_final_evaluation_executed", "BOOL", "false"),
    ("graph.isolation", "production_to_evaluator_dependency_count", "MAX", "0"),
    ("replay.no_goldens", "replay_without_goldens_pass", "BOOL", "true"),
    ("quality.mutations", "all_v2_mutations_blocked", "BOOL", "true"),
    ("quality.windows", "windows_development_gate_pass", "BOOL", "true"),
    ("quality.karina", "karina_development_gate_pass", "BOOL", "true"),
)


def evaluate_pre_freeze_gate_v2(raw_evidence) -> JavaPreFreezeV2Report:
    keys = {item[1] for item in M344_PRE_FREEZE_V2_SPECS}
    if set(raw_evidence) != keys:
        raise ValueError("M-34.4 pre-freeze evidence schema mismatch")
    criteria = tuple(
        _criterion(*spec, raw_evidence[spec[1]]) for spec in M344_PRE_FREEZE_V2_SPECS
    )
    failed = sum(item.status != "PASS" for item in criteria)
    body = {
        "schema_version": 2,
        "criteria": criteria,
        "mandatory_count": len(criteria),
        "pass_count": len(criteria) - failed,
        "fail_count": failed,
        "decision": (
            JavaPreFreezeV2Decision.READY_FOR_FRESH_FREEZE
            if failed == 0
            else JavaPreFreezeV2Decision.BLOCKED
        ),
        "raw_evidence_hash": content_hash(raw_evidence),
    }
    return JavaPreFreezeV2Report(**body, report_hash=content_hash(body))


def run_m344_full_gate_mutations(passing_evidence):
    mutations = {
        "golden_parameter": {"production_api_rejects_evaluation_arguments": False},
        "golden_file_read": {"production_golden_file_read_count": 1},
        "expected_supported_dependency": {
            "production_golden_substitution_invariant": False
        },
        "zero_real_callables": {"real_callable_target_count": 0},
        "package_info_counted": {"package_info_callable_file_count": 1},
        "java_release_mismatch": {"release_consistency_pass": False},
        "synthetic_dominance": {
            "synthetic_target_share": {"numerator": 51, "denominator": 100}
        },
        "forged_user_reviewer": {"automated_reviewer_not_user": False},
        "incomplete_frozen_paths": {"frozen_path_coverage_complete": False},
        "caller_snapshot": {"freeze_snapshots_git_derived": False},
        "prefix_confusion": {"freeze_prefix_boundary_safe": False},
        "final_hash_leak": {"final_hashes_absent_from_f13": False},
    }
    result = []
    for name, changes in mutations.items():
        row = {**passing_evidence, **changes, "all_v2_mutations_blocked": True}
        report = evaluate_pre_freeze_gate_v2(row)
        if report.decision is not JavaPreFreezeV2Decision.BLOCKED:
            raise AssertionError(f"M-34.4 mutation did not block: {name}")
        result.append((name, report.report_hash))
    return tuple(result)


def _criterion(identifier, key, operator, threshold, value):
    measured = str(value).lower() if isinstance(value, bool) else str(value)
    passed = False
    if operator == "BOOL":
        passed = isinstance(value, bool) and value is (threshold == "true")
    else:
        try:
            if isinstance(value, dict):
                if set(value) != {"numerator", "denominator"}:
                    raise ValueError
                denominator = int(value["denominator"])
                number = (
                    None
                    if denominator == 0
                    else Decimal(int(value["numerator"])) / denominator
                )
                measured = "N/A" if number is None else f"{number:.6f}"
            else:
                number = Decimal(str(value))
            limit = Decimal(threshold)
            passed = number is not None and (
                number >= limit if operator == "MIN" else number <= limit
            )
        except (ArithmeticError, TypeError, ValueError):
            passed = False
    evidence = {
        "criterion_id": identifier,
        "evidence_key": key,
        "value": value,
        "threshold": threshold,
        "operator": operator,
    }
    return JavaPreFreezeV2Criterion(
        identifier,
        key,
        measured,
        f"{operator}:{threshold}",
        "PASS" if passed else "FAIL",
        content_hash(evidence),
    )
