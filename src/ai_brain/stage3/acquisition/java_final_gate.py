"""Frozen count-first outcome gates for untouched Java runs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, StrEnum

from ai_brain.stage2.facts.canonical import content_hash


class JavaFinalOutcome(str, Enum):
    OUTCOME_A = "OUTCOME_A_JAVA_FRESH_FREEZE_PASSES"
    OUTCOME_B = "OUTCOME_B_SAFE_ORACLE_FREE_SUBSET"
    OUTCOME_C = "OUTCOME_C_BLOCKED"


@dataclass(frozen=True)
class JavaFinalGateCriterion:
    criterion_id: str
    measured_value: str
    threshold: str
    status: str
    evidence_hash: str


@dataclass(frozen=True)
class JavaFinalGateReport:
    outcome: JavaFinalOutcome
    criteria: tuple[JavaFinalGateCriterion, ...]
    pass_count: int
    fail_count: int
    raw_evidence_hash: str
    report_hash: str


M344_FINAL_GATE_SPECS = (
    ("corpus.files", "real_callable_source_file_count", "MIN", "60"),
    ("corpus.callables", "real_callable_target_count", "MIN", "1500"),
    ("corpus.receivers", "real_receiver_type_count", "MIN", "150"),
    ("corpus.packages", "real_package_count", "MIN", "12"),
    ("corpus.overloads", "real_overload_group_count", "MIN", "100"),
    ("corpus.constructors", "real_constructor_count", "MIN", "50"),
    ("corpus.generics", "real_generic_method_count", "MIN", "100"),
    ("corpus.throws", "real_throws_declaration_count", "MIN", "100"),
    ("corpus.nested", "real_nested_member_target_count", "MIN", "25"),
    ("location.precision", "real_location_precision", "MIN", "1.000000"),
    ("location.recall", "real_location_recall", "MIN", "0.950000"),
    ("semantic.precision", "real_semantic_precision", "MIN", "1.000000"),
    ("semantic.recall", "real_semantic_recall", "MIN", "0.950000"),
    ("trust.precision", "real_trust_precision", "MIN", "1.000000"),
    ("trust.wrong", "wrong_trusted_count", "MAX", "0"),
    ("trust.coverage", "real_trust_coverage", "MIN", "0.800000"),
    ("evidence.exact", "trusted_field_evidence_exactness", "MIN", "1.000000"),
    ("resolution.exact", "resolution_oracle_agreement", "MIN", "1.000000"),
    ("duplicates.none", "duplicate_derived_trusted", "MAX", "0"),
    ("release.exact", "release_consistency_pass", "BOOL", "true"),
    ("production.oracle_free", "oracle_free_production_pass", "BOOL", "true"),
    ("replay.no_goldens", "replay_without_goldens_pass", "BOOL", "true"),
    ("process.safe", "process_audit_pass", "BOOL", "true"),
    ("pack.installed", "approved_pack_installation_pass", "BOOL", "true"),
    ("cross_platform.bytes", "cross_platform_byte_identity", "BOOL", "true"),
    ("freeze.integrity", "freeze_integrity_pass", "BOOL", "true"),
)


_SAFETY_KEYS = frozenset(
    {
        "wrong_trusted_count",
        "release_consistency_pass",
        "oracle_free_production_pass",
        "replay_without_goldens_pass",
        "process_audit_pass",
        "freeze_integrity_pass",
    }
)


def evaluate_java_final_gate(raw: dict) -> JavaFinalGateReport:
    if set(raw) != {item[1] for item in M344_FINAL_GATE_SPECS}:
        raise ValueError("final Java gate evidence schema mismatch")
    criteria = []
    safety_pass = True
    for identifier, key, operator, threshold in M344_FINAL_GATE_SPECS:
        value = raw[key]
        measured = _display(value)
        passed = _compare(value, operator, threshold)
        if key in _SAFETY_KEYS:
            safety_pass = safety_pass and passed
        body = {
            "criterion_id": identifier,
            "measured_value": measured,
            "threshold": f"{operator}:{threshold}",
            "status": "PASS" if passed else "FAIL",
        }
        criteria.append(
            JavaFinalGateCriterion(**body, evidence_hash=content_hash((key, value)))
        )
    failures = sum(item.status == "FAIL" for item in criteria)
    if not safety_pass:
        outcome = JavaFinalOutcome.OUTCOME_C
    elif failures:
        outcome = JavaFinalOutcome.OUTCOME_B
    else:
        outcome = JavaFinalOutcome.OUTCOME_A
    body = {
        "outcome": outcome,
        "criteria": tuple(criteria),
        "pass_count": len(criteria) - failures,
        "fail_count": failures,
        "raw_evidence_hash": content_hash(raw),
    }
    return JavaFinalGateReport(**body, report_hash=content_hash(body))


def _display(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, dict):
        denominator = value["denominator"]
        return "N/A" if denominator == 0 else f"{value['numerator'] / denominator:.6f}"
    return str(value)


def _compare(value, operator: str, threshold: str) -> bool:
    if operator == "BOOL":
        return isinstance(value, bool) and value is (threshold == "true")
    if isinstance(value, dict):
        if value["denominator"] == 0:
            return False
        measured = value["numerator"] / value["denominator"]
    else:
        measured = float(value)
    target = float(threshold)
    return measured >= target if operator == "MIN" else measured <= target


class M336FinalOutcome(StrEnum):
    OUTCOME_A = "OUTCOME_A"
    OUTCOME_B = "OUTCOME_B"
    OUTCOME_C = "OUTCOME_C"


@dataclass(frozen=True)
class M336FinalCriterion:
    criterion_id: str
    measured_value: str
    threshold: str
    safety_critical: bool
    status: str


@dataclass(frozen=True)
class M336FinalGateReport:
    schema_version: int
    criteria: tuple[M336FinalCriterion, ...]
    safety_failure_count: int
    quality_failure_count: int
    outcome: M336FinalOutcome
    evidence_hash: str
    report_hash: str


M336_FINAL_GATE_SPECS = (
    ("corpus.files", "real_callable_source_file_count", "MIN", "100", False),
    ("corpus.targets", "real_callable_target_count", "MIN", "2000", False),
    ("corpus.types", "real_receiver_type_count", "MIN", "175", False),
    ("corpus.packages", "real_package_count", "MIN", "15", False),
    ("corpus.overloads", "real_overload_group_count", "MIN", "125", False),
    ("corpus.constructors", "real_constructor_count", "MIN", "75", False),
    ("corpus.generics", "real_generic_method_count", "MIN", "100", False),
    ("corpus.throws", "real_throws_declaration_count", "MIN", "100", False),
    ("corpus.nested", "real_nested_member_target_count", "MIN", "25", False),
    ("corpus.synthetic", "synthetic_target_count", "MAX", "0", True),
    ("corpus.root_share", "maximum_root_target_fraction", "MAX", "0.800000", False),
    ("location.precision", "location_precision", "MIN", "1.000000", False),
    ("location.recall", "location_recall", "MIN", "0.950000", False),
    ("semantic.precision", "semantic_precision", "MIN", "1.000000", False),
    ("semantic.recall", "semantic_recall", "MIN", "0.950000", False),
    ("trust.precision", "trust_precision", "MIN", "1.000000", True),
    ("trust.wrong", "wrong_trusted_count", "MAX", "0", True),
    ("trust.coverage", "trust_coverage", "MIN", "0.800000", False),
    ("evidence.exact", "field_evidence_exactness", "MIN", "1.000000", True),
    ("resolution.exact", "resolution_agreement", "MIN", "1.000000", True),
    ("packability.coverage", "trusted_packability_coverage", "MIN", "1.000000", True),
    ("packability.post", "post_trust_pack_failures", "MAX", "0", True),
    ("packability.overload", "legal_overloads_blocked", "MAX", "0", True),
    ("diagnostics.header", "trusted_header_blocking_diagnostics", "MAX", "0", True),
    ("platform.differences", "platform_independent_differences", "MAX", "0", True),
    ("isolation.dependencies", "production_evaluator_dependencies", "MAX", "0", True),
    ("isolation.golden_reads", "production_golden_reads", "MAX", "0", True),
    ("corpus.overlap", "final_source_overlap", "MAX", "0", True),
    ("candidate.replay", "candidate_replay_pass", "BOOL", "true", True),
    ("replay.mutations", "replay_mutations_all_rejected", "BOOL", "true", True),
    ("runtime.no_sources", "runtime_without_sources_pass", "BOOL", "true", True),
    ("freeze.precommit", "precommit_freeze_integrity_pass", "BOOL", "true", True),
)


def evaluate_m336_final_gate(evidence) -> M336FinalGateReport:
    expected = {item[1] for item in M336_FINAL_GATE_SPECS}
    if set(evidence) != expected:
        raise ValueError("M-33.6 final gate evidence schema mismatch")
    criteria = tuple(
        _criterion(identifier, evidence[key], operator, threshold, safety)
        for identifier, key, operator, threshold, safety in M336_FINAL_GATE_SPECS
    )
    safety_failures = sum(
        item.safety_critical and item.status != "PASS" for item in criteria
    )
    quality_failures = sum(
        not item.safety_critical and item.status != "PASS" for item in criteria
    )
    if safety_failures:
        outcome = M336FinalOutcome.OUTCOME_C
    elif quality_failures:
        outcome = M336FinalOutcome.OUTCOME_B
    else:
        outcome = M336FinalOutcome.OUTCOME_A
    body = {
        "schema_version": 1,
        "criteria": criteria,
        "safety_failure_count": safety_failures,
        "quality_failure_count": quality_failures,
        "outcome": outcome,
        "evidence_hash": content_hash(evidence),
    }
    return M336FinalGateReport(**body, report_hash=content_hash(body))


def _criterion(identifier, value, operator, threshold, safety):
    measured = str(value).lower() if isinstance(value, bool) else str(value)
    if operator == "BOOL":
        passed = isinstance(value, bool) and value is (threshold == "true")
    else:
        try:
            observed = Decimal(str(value))
            limit = Decimal(threshold)
            passed = observed >= limit if operator == "MIN" else observed <= limit
        except (ArithmeticError, TypeError, ValueError):
            passed = False
    return M336FinalCriterion(
        identifier,
        measured,
        f"{operator}:{threshold}",
        safety,
        "PASS" if passed else "FAIL",
    )
