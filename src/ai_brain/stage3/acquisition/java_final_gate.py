"""Frozen count-first outcome gate for the untouched M-34.4 Java run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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
