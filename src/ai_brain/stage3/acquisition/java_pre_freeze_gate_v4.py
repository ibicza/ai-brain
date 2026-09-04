"""M-33.6 executable gate for consuming one untouched final Java corpus."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash


class M336PreFreezeDecision(StrEnum):
    READY_FOR_FINAL_ACQUISITION = "READY_FOR_FINAL_ACQUISITION"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class M336PreFreezeCriterion:
    criterion_id: str
    evidence_key: str
    measured_value: str
    threshold: str
    status: str
    evidence_hash: str


@dataclass(frozen=True)
class M336PreFreezeGateV4:
    schema_version: int
    criteria: tuple[M336PreFreezeCriterion, ...]
    mandatory_count: int
    pass_count: int
    fail_count: int
    decision: M336PreFreezeDecision
    raw_evidence_hash: str
    report_hash: str


M336_PRE_FREEZE_V4_SPECS = (
    ("m335.ready", "m335_gate_ready", "BOOL", "true"),
    ("m335.thresholds", "m335_thresholds_pass", "BOOL", "true"),
    ("m335.cross_platform", "candidate_pack_cross_platform_identical", "BOOL", "true"),
    ("m335.overloads", "legal_overloads_blocked", "MAX", "0"),
    ("bundle.mutations", "canonical_bundle_mutations_accepted", "MAX", "0"),
    ("bundle.timestamp", "timestamp_independence_matrix_pass", "BOOL", "true"),
    ("packability.mutations", "packability_mutations_accepted", "MAX", "0"),
    ("packability.trust", "trusted_packability_coverage", "MIN", "1.000000"),
    ("roles.unknown", "unknown_final_roles_accepted", "MAX", "0"),
    ("roles.derived", "protected_disclosure_tokens_derived", "BOOL", "true"),
    ("references.scope", "scoped_exact_reference_tests_pass", "BOOL", "true"),
    ("diagnostics.header", "trusted_header_blocking_diagnostics", "MAX", "0"),
    ("applicability.closure", "strict_applicability_tests_pass", "BOOL", "true"),
    ("freeze.protocol", "m336_freeze_protocol_tests_pass", "BOOL", "true"),
    ("isolation.oracle", "production_evaluator_dependency_count", "MAX", "0"),
    ("isolation.goldens", "production_golden_read_count", "MAX", "0"),
    ("quality.ruff", "ruff_pass", "BOOL", "true"),
    ("quality.targeted", "targeted_tests_pass", "BOOL", "true"),
    ("quality.windows", "windows_full_suite_pass", "BOOL", "true"),
    ("quality.karina", "karina_full_suite_pass", "BOOL", "true"),
    ("quality.base", "exact_e14_base", "BOOL", "true"),
    ("quality.no_final", "final_source_acquired_or_inspected", "BOOL", "false"),
    ("policy.content", "moral_or_topic_policy_added", "BOOL", "false"),
)


def evaluate_m336_pre_freeze_gate_v4(raw_evidence) -> M336PreFreezeGateV4:
    keys = {item[1] for item in M336_PRE_FREEZE_V4_SPECS}
    if set(raw_evidence) != keys:
        raise ValueError("M-33.6 pre-freeze V4 evidence schema mismatch")
    criteria = tuple(
        _criterion(*spec, raw_evidence[spec[1]]) for spec in M336_PRE_FREEZE_V4_SPECS
    )
    failed = sum(item.status != "PASS" for item in criteria)
    body = {
        "schema_version": 4,
        "criteria": criteria,
        "mandatory_count": len(criteria),
        "pass_count": len(criteria) - failed,
        "fail_count": failed,
        "decision": (
            M336PreFreezeDecision.READY_FOR_FINAL_ACQUISITION
            if failed == 0
            else M336PreFreezeDecision.BLOCKED
        ),
        "raw_evidence_hash": content_hash(raw_evidence),
    }
    return M336PreFreezeGateV4(**body, report_hash=content_hash(body))


def run_m336_gate_mutations(passing_evidence):
    blocked = []
    for _criterion_id, key, operator, threshold in M336_PRE_FREEZE_V4_SPECS:
        if operator == "BOOL":
            mutation = threshold != "true"
        elif operator == "MAX":
            mutation = str(Decimal(threshold) + 1)
        else:
            mutation = str(Decimal(threshold) - Decimal("0.000001"))
        report = evaluate_m336_pre_freeze_gate_v4({**passing_evidence, key: mutation})
        if report.decision is not M336PreFreezeDecision.BLOCKED:
            raise AssertionError(f"M-33.6 gate mutation did not block: {key}")
        blocked.append((key, report.report_hash))
    return tuple(blocked)


def _criterion(identifier, key, operator, threshold, value):
    measured = str(value).lower() if isinstance(value, bool) else str(value)
    if operator == "BOOL":
        passed = isinstance(value, bool) and value is (threshold == "true")
    else:
        try:
            number = Decimal(str(value))
            limit = Decimal(threshold)
            passed = number >= limit if operator == "MIN" else number <= limit
        except (ArithmeticError, TypeError, ValueError):
            passed = False
    evidence = {
        "criterion_id": identifier,
        "evidence_key": key,
        "value": value,
        "threshold": threshold,
        "operator": operator,
    }
    return M336PreFreezeCriterion(
        identifier,
        key,
        measured,
        f"{operator}:{threshold}",
        "PASS" if passed else "FAIL",
        content_hash(evidence),
    )
