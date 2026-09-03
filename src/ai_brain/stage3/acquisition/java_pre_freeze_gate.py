"""Single derived, fail-closed authority for Java pre-freeze readiness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash


class PreFreezeDecision(StrEnum):
    READY_FOR_FRESH_FREEZE = "READY_FOR_FRESH_FREEZE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PreFreezeCriterion:
    criterion_id: str
    measured_numerator: int | None
    measured_denominator: int | None
    boolean_result: bool | None
    measured_value: str
    threshold: str
    mandatory: bool
    status: str
    evidence_hash: str


@dataclass(frozen=True)
class PreFreezeGateReport:
    schema_version: int
    raw_evidence_hash: str
    criteria: tuple[PreFreezeCriterion, ...]
    mandatory_count: int
    pass_count: int
    fail_count: int
    decision: PreFreezeDecision
    criteria_hash: str
    report_hash: str


_SPECS = (
    ("corpus.source_files", "corpus_source_file_count", "MIN", "50"),
    ("corpus.real_source_files", "corpus_real_source_file_count", "MIN", "50"),
    ("corpus.packages", "corpus_package_count", "MIN", "5"),
    ("corpus.libraries", "corpus_library_count", "MIN", "2"),
    ("corpus.callables", "corpus_callable_count", "MIN", "1500"),
    ("corpus.positive", "corpus_positive_count", "MIN", "500"),
    ("corpus.semantic_negative", "corpus_semantic_negative_count", "MIN", "500"),
    ("corpus.overloads", "legal_overload_group_count", "MIN", "100"),
    ("corpus.constructors", "constructor_count", "MIN", "50"),
    ("corpus.generic_methods", "generic_method_count", "MIN", "50"),
    ("corpus.intersection_bounds", "intersection_bound_method_count", "MIN", "25"),
    ("corpus.throws", "throws_declaration_count", "MIN", "50"),
    ("corpus.nested", "nested_member_case_count", "MIN", "25"),
    ("corpus.hash_disjoint", "prior_source_hash_intersection_count", "MAX", "0"),
    ("location.precision", "location_precision", "MIN", "1.000000"),
    ("location.recall", "location_recall", "MIN", "0.950000"),
    ("semantic.precision", "semantic_precision", "MIN", "1.000000"),
    ("semantic.recall", "semantic_recall", "MIN", "0.950000"),
    ("semantic.wrong_content", "correct_location_wrong_content", "MAX", "0"),
    ("trust.precision", "trust_precision", "MIN", "1.000000"),
    ("trust.wrong", "wrong_trusted_count", "MAX", "0"),
    ("trust.coverage", "trust_coverage", "MIN", "0.800000"),
    ("resolution.oracle_agreement", "resolution_oracle_agreement", "MIN", "1.000000"),
    ("resolution.invalid_bound_fallback", "invalid_bound_object_fallback_count", "MAX", "0"),
    ("resolution.unresolved_throws", "unresolved_throws_accepted_count", "MAX", "0"),
    ("resolution.inaccessible", "inaccessible_types_accepted_count", "MAX", "0"),
    ("resolution.missing_intersection", "missing_intersection_bound_count", "MAX", "0"),
    ("policy.unmatched", "policy_unmatched_field_count", "MAX", "0"),
    ("policy.multiple", "policy_multiply_matched_field_count", "MAX", "0"),
    ("policy.unknown", "policy_unknown_proposal_field_count", "MAX", "0"),
    ("policy.zero_mandatory", "policy_zero_mandatory_rule_count", "MAX", "0"),
    ("evidence.missing", "evidence_missing_count", "MAX", "0"),
    ("evidence.extra", "evidence_extra_count", "MAX", "0"),
    ("evidence.duplicate", "evidence_duplicate_count", "MAX", "0"),
    ("evidence.wrong", "evidence_wrong_count", "MAX", "0"),
    ("evidence.transform_exactness", "transformation_exactness", "MIN", "1.000000"),
    ("evidence.oracle_agreement", "oracle_field_agreement", "MIN", "1.000000"),
    ("ir.hardcoded_object_type", "hardcoded_java_object_type_count", "MAX", "0"),
    ("ir.void_constructor", "void_constructor_mapping_pass", "BOOL", "true"),
    ("overload.legal_conflicts", "legal_overload_conflict_count", "MAX", "0"),
    ("conflict.precision", "conflict_precision", "MIN", "1.000000"),
    ("conflict.recall", "conflict_recall", "MIN", "1.000000"),
    ("duplicates.physical_rate", "physical_duplicate_rate", "MAX", "0.000000"),
    ("duplicates.trusted", "duplicate_derived_trusted_count", "MAX", "0"),
    ("replay.fresh_process", "fresh_process_replay_pass", "BOOL", "true"),
    ("replay.newline_closure", "newline_replay_pass", "BOOL", "true"),
    ("replay.mutations", "standalone_mutations_all_rejected", "BOOL", "true"),
    ("side_effect.socket", "socket_attempt_count", "MAX", "0"),
    ("side_effect.subprocess", "unexpected_subprocess_count", "MAX", "0"),
    ("side_effect.source_execution", "source_execution_count", "MAX", "0"),
    ("side_effect.annotation", "annotation_processor_invocation_count", "MAX", "0"),
    ("side_effect.fact_memory", "fact_memory_write_count", "MAX", "0"),
    ("side_effect.rule_memory", "rule_memory_write_count", "MAX", "0"),
    ("side_effect.registry", "registry_mutation_count", "MAX", "0"),
    ("side_effect.pytorch", "pytorch_imported", "BOOL", "false"),
    ("seal.valid", "golden_seal_valid", "BOOL", "true"),
    ("parser.valid", "parser_artifact_valid", "BOOL", "true"),
    ("meta.full_gate", "full_gate_mutations_all_blocked", "BOOL", "true"),
    ("platform.byte_identity", "cross_platform_artifacts_byte_identical", "BOOL", "true"),
    ("quality.ruff", "ruff_pass", "BOOL", "true"),
    ("quality.targeted", "targeted_tests_pass", "BOOL", "true"),
    ("quality.windows_full", "full_suite_windows_pass", "BOOL", "true"),
    ("quality.karina_full", "full_suite_karina_pass", "BOOL", "true"),
    ("release.windows_clean", "windows_worktree_clean", "BOOL", "true"),
    ("release.karina_clean", "karina_worktree_clean", "BOOL", "true"),
    ("release.upstream", "local_remote_sha_equal", "BOOL", "true"),
    ("release.unmerged", "branch_pushed_without_merge", "BOOL", "true"),
    ("release.m33_ancestry", "m33_outside_ancestry", "BOOL", "true"),
    ("release.policy_layers", "policy_layers_unchanged", "BOOL", "true"),
    ("evaluation.untouched", "untouched_final_evaluation_executed", "BOOL", "false"),
)


def evaluate_pre_freeze_gate(raw_evidence) -> PreFreezeGateReport:
    if set(raw_evidence) != {item[1] for item in _SPECS}:
        missing = sorted({item[1] for item in _SPECS} - set(raw_evidence))
        extra = sorted(set(raw_evidence) - {item[1] for item in _SPECS})
        raise ValueError(f"pre-freeze raw evidence schema mismatch: {missing=} {extra=}")
    criteria = tuple(
        _criterion(identifier, key, operator, threshold, raw_evidence[key])
        for identifier, key, operator, threshold in _SPECS
    )
    failed = sum(item.status != "PASS" for item in criteria if item.mandatory)
    decision = (
        PreFreezeDecision.READY_FOR_FRESH_FREEZE
        if failed == 0
        else PreFreezeDecision.BLOCKED
    )
    body = {
        "schema_version": 1,
        "raw_evidence_hash": content_hash(raw_evidence),
        "criteria": criteria,
        "mandatory_count": sum(item.mandatory for item in criteria),
        "pass_count": sum(item.status == "PASS" for item in criteria),
        "fail_count": failed,
        "decision": decision,
        "criteria_hash": content_hash(criteria),
    }
    return PreFreezeGateReport(**body, report_hash=content_hash(body))


def verify_pre_freeze_gate_report(report, raw_evidence) -> None:
    if evaluate_pre_freeze_gate(raw_evidence) != report:
        raise ValueError("pre-freeze decision or criterion report was altered")


def load_pre_freeze_gate_report(path: Path) -> tuple[dict, PreFreezeGateReport]:
    row = json.loads(path.read_text(encoding="utf-8"))
    if set(row) != {"raw_evidence", "gate"}:
        raise ValueError("pre-freeze report envelope mismatch")
    gate = dict(row["gate"])
    criteria = tuple(
        PreFreezeCriterion(**item) for item in gate.pop("criteria")
    )
    decision = PreFreezeDecision(gate.pop("decision"))
    report = PreFreezeGateReport(
        **gate,
        criteria=criteria,
        decision=decision,
    )
    verify_pre_freeze_gate_report(report, row["raw_evidence"])
    return row["raw_evidence"], report


def run_full_gate_meta_mutations(raw_evidence):
    mutations = {
        "wrong_trusted": {"wrong_trusted_count": 1},
        "missing_expected_proposal": {
            "semantic_recall": {"numerator": 949, "denominator": 1000}
        },
        "spurious_proposal": {
            "semantic_precision": {"numerator": 999, "denominator": 1000}
        },
        "correct_location_wrong_content": {"correct_location_wrong_content": 1},
        "wrong_source_location": {
            "location_precision": {"numerator": 999, "denominator": 1000}
        },
        "missing_field_requirement": {"evidence_missing_count": 1},
        "extra_evidence_receipt": {"evidence_extra_count": 1},
        "wrong_evidence_value": {"evidence_wrong_count": 1},
        "missed_seeded_conflict": {
            "conflict_recall": {"numerator": 1, "denominator": 2}
        },
        "spurious_conflict": {
            "conflict_precision": {"numerator": 1, "denominator": 2}
        },
        "zero_trusted_proposals": {
            "trust_coverage": {"numerator": 0, "denominator": 1}
        },
        "resolver_mismatch": {
            "resolution_oracle_agreement": {
                "numerator": 999,
                "denominator": 1000,
            }
        },
        "unexpected_subprocess": {"unexpected_subprocess_count": 1},
        "socket_attempt": {"socket_attempt_count": 1},
        "changed_golden_seal": {"golden_seal_valid": False},
        "changed_parser_artifact": {"parser_artifact_valid": False},
        "failed_standalone_replay": {"fresh_process_replay_pass": False},
    }
    results = []
    for name, changes in mutations.items():
        mutated = {**raw_evidence, **changes, "full_gate_mutations_all_blocked": True}
        report = evaluate_pre_freeze_gate(mutated)
        if report.decision is not PreFreezeDecision.BLOCKED:
            raise AssertionError(f"full-gate mutation did not block: {name}")
        results.append((name, report))
    return tuple(results)


def _criterion(identifier, key, operator, threshold, value):
    numerator = None
    denominator = None
    boolean = None
    if operator == "BOOL":
        boolean = value if isinstance(value, bool) else None
        expected = threshold == "true"
        passed = boolean is not None and boolean is expected
        measured = str(value).lower()
    else:
        try:
            if isinstance(value, dict):
                if set(value) != {"numerator", "denominator"}:
                    raise ValueError("ratio evidence envelope mismatch")
                numerator = int(value["numerator"])
                denominator = int(value["denominator"])
                if numerator < 0 or denominator < 0:
                    raise ValueError("negative gate ratio count")
                if denominator == 0:
                    measured = "N/A"
                    number = None
                else:
                    number = Decimal(numerator) / Decimal(denominator)
                    measured = f"{number:.6f}"
            else:
                measured = str(value)
                number = Decimal(measured)
                if isinstance(value, int) and not isinstance(value, bool):
                    numerator = value
            limit = Decimal(threshold)
        except (InvalidOperation, TypeError, ValueError):
            passed = False
        else:
            passed = number is not None and (
                number >= limit if operator == "MIN" else number <= limit
            )
    evidence = {
        "criterion_id": identifier,
        "raw_key": key,
        "value": value,
        "threshold": threshold,
        "operator": operator,
    }
    return PreFreezeCriterion(
        identifier,
        numerator,
        denominator,
        boolean,
        measured,
        f"{operator}:{threshold}",
        True,
        "PASS" if passed else "FAIL",
        content_hash(evidence),
    )
