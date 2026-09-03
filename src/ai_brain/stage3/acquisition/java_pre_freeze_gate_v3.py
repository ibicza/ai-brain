"""M-33.5 development-readiness gate derived from failed M-34.4 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash


class M335PreFreezeDecision(StrEnum):
    READY_FOR_FRESH_JAVA_FREEZE = "READY_FOR_FRESH_JAVA_FREEZE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class M335PreFreezeCriterion:
    criterion_id: str
    evidence_key: str
    measured_value: str
    threshold: str
    status: str
    evidence_hash: str


@dataclass(frozen=True)
class M335PreFreezeGateV3:
    schema_version: int
    criteria: tuple[M335PreFreezeCriterion, ...]
    mandatory_count: int
    pass_count: int
    fail_count: int
    decision: M335PreFreezeDecision
    raw_evidence_hash: str
    report_hash: str


M335_PRE_FREEZE_V3_SPECS = (
    ("oracle.dependencies", "production_evaluator_dependency_count", "MAX", "0"),
    ("oracle.golden_reads", "production_golden_read_count", "MAX", "0"),
    (
        "oracle.substitution",
        "production_evaluator_substitution_invariant",
        "BOOL",
        "true",
    ),
    ("identity.aliases", "classified_alias_collision_count", "MIN", "6"),
    ("identity.old_conflicts", "classified_prior_conflict_count", "MIN", "48"),
    ("identity.unclassified", "unclassified_conflict_count", "MAX", "0"),
    ("identity.legal_blocked", "legal_overloads_blocked_as_conflicts", "MAX", "0"),
    ("identity.collisions", "unresolved_authoritative_identity_collisions", "MAX", "0"),
    ("identity.alias_authority", "search_aliases_used_as_authority", "MAX", "0"),
    ("packability.coverage", "trusted_packability_coverage", "MIN", "1.000000"),
    ("packability.compile", "candidate_pack_compilation_pass", "BOOL", "true"),
    ("packability.replay", "candidate_pack_replay_pass", "BOOL", "true"),
    ("packability.install", "candidate_pack_installation_pass", "BOOL", "true"),
    ("packability.runtime", "candidate_runtime_query_pass", "BOOL", "true"),
    ("packability.post_trust", "post_trust_identity_failure_count", "MAX", "0"),
    ("determinism.matrix", "permutation_matrix_pass", "BOOL", "true"),
    ("determinism.platform", "cross_platform_component_match", "BOOL", "true"),
    ("determinism.first", "first_divergent_stage_none", "BOOL", "true"),
    ("determinism.differences", "platform_independent_difference_count", "MAX", "0"),
    ("semantic.location_precision", "location_precision", "MIN", "1.000000"),
    ("semantic.location_recall", "location_recall", "MIN", "0.950000"),
    ("semantic.precision", "semantic_precision", "MIN", "1.000000"),
    ("semantic.recall", "semantic_recall", "MIN", "0.950000"),
    ("trust.precision", "automatic_trust_precision", "MIN", "1.000000"),
    ("trust.wrong", "wrong_trusted_count", "MAX", "0"),
    ("trust.coverage", "trust_coverage", "MIN", "0.800000"),
    ("evidence.exactness", "trusted_field_evidence_exactness", "MIN", "1.000000"),
    ("resolution.agreement", "resolution_agreement", "MIN", "1.000000"),
    ("freeze.roles", "role_aware_verifier_pass", "BOOL", "true"),
    ("freeze.neutral", "neutral_blob_reuse_pass", "BOOL", "true"),
    ("freeze.mutations", "all_disclosure_mutations_blocked", "BOOL", "true"),
    ("freeze.denylist", "disclosed_corpus_denylist_complete", "BOOL", "true"),
    ("security.subprocess", "unexpected_subprocess_count", "MAX", "0"),
    ("security.socket", "socket_attempt_count", "MAX", "0"),
    ("security.os_system", "os_system_attempt_count", "MAX", "0"),
    ("security.source_execution", "source_execution_count", "MAX", "0"),
    (
        "security.generated_execution",
        "generated_class_execution_count",
        "MAX",
        "0",
    ),
    (
        "security.annotation_processors",
        "annotation_processor_invocation_count",
        "MAX",
        "0",
    ),
    ("security.fact_memory", "fact_memory_write_attempts", "MAX", "0"),
    ("security.rule_memory", "rule_memory_write_attempts", "MAX", "0"),
    ("security.skill_registry", "skill_registry_write_attempts", "MAX", "0"),
    (
        "security.provider_registry",
        "provider_registry_mutation_attempts",
        "MAX",
        "0",
    ),
    (
        "security.domain_registry",
        "domain_registry_preinstall_mutation_attempts",
        "MAX",
        "0",
    ),
    ("security.torch", "torch_imported", "BOOL", "false"),
    ("quality.ruff", "ruff_pass", "BOOL", "true"),
    ("quality.targeted", "targeted_tests_pass", "BOOL", "true"),
    ("quality.windows", "windows_full_suite_pass", "BOOL", "true"),
    ("quality.karina", "karina_full_suite_pass", "BOOL", "true"),
    ("quality.clean", "worktrees_clean", "BOOL", "true"),
    ("quality.upstream", "branch_upstream_equal", "BOOL", "true"),
    ("quality.no_final", "new_untouched_final_evaluation_executed", "BOOL", "false"),
)


def evaluate_m335_pre_freeze_gate_v3(raw_evidence) -> M335PreFreezeGateV3:
    keys = {item[1] for item in M335_PRE_FREEZE_V3_SPECS}
    if set(raw_evidence) != keys:
        raise ValueError("M-33.5 pre-freeze V3 evidence schema mismatch")
    criteria = tuple(
        _criterion(*spec, raw_evidence[spec[1]]) for spec in M335_PRE_FREEZE_V3_SPECS
    )
    failed = sum(item.status != "PASS" for item in criteria)
    body = {
        "schema_version": 3,
        "criteria": criteria,
        "mandatory_count": len(criteria),
        "pass_count": len(criteria) - failed,
        "fail_count": failed,
        "decision": (
            M335PreFreezeDecision.READY_FOR_FRESH_JAVA_FREEZE
            if failed == 0
            else M335PreFreezeDecision.BLOCKED
        ),
        "raw_evidence_hash": content_hash(raw_evidence),
    }
    return M335PreFreezeGateV3(**body, report_hash=content_hash(body))


def run_m335_gate_mutations(passing_evidence):
    result = []
    for _criterion_id, key, operator, expected in M335_PRE_FREEZE_V3_SPECS:
        if operator == "BOOL":
            mutation = expected != "true"
        elif operator == "MAX":
            mutation = str(Decimal(expected) + 1)
        else:
            mutation = str(Decimal(expected) - Decimal("0.000001"))
        report = evaluate_m335_pre_freeze_gate_v3({**passing_evidence, key: mutation})
        if report.decision is not M335PreFreezeDecision.BLOCKED:
            raise AssertionError(f"M-33.5 gate mutation did not block: {key}")
        result.append((key, report.report_hash))
    return tuple(result)


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
    return M335PreFreezeCriterion(
        identifier,
        key,
        measured,
        f"{operator}:{threshold}",
        "PASS" if passed else "FAIL",
        content_hash(evidence),
    )
