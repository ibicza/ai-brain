"""Closed M-33.6a development-readiness gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash


class M336AReadinessDecision(StrEnum):
    READY_FOR_FRESH_JAVA_FREEZE_V2 = "READY_FOR_FRESH_JAVA_FREEZE_V2"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class M336AReadinessGate:
    criteria: tuple[tuple[str, bool], ...]
    pass_count: int
    mandatory_count: int
    failed_criteria: tuple[str, ...]
    decision: M336AReadinessDecision
    gate_hash: str


_BOOLEAN_CRITERIA = (
    "artifact_coordinate_verification",
    "archive_pom_checksum_verification",
    "immutable_scm_revision_verification",
    "exact_license_text_verification",
    "eligible_source_correspondence",
    "every_candidate_has_typed_receipt",
    "optional_rejection_does_not_abort",
    "typed_role_manifest_roundtrip",
    "historical_role_manifest_matches",
    "exact_historical_chain",
    "corrected_protocol_integrity",
    "historical_outcome_remains_c",
    "ruff",
    "targeted_tests",
    "windows_full_suite",
    "karina_full_suite",
    "windows_slow_test_three_of_three",
    "worktrees_clean",
    "branch_upstream_equal",
)

_ZERO_CRITERIA = (
    "conflicting_evidence_accepted",
    "pom_only_auto_verified",
    "selector_rerun_count",
    "metrics_used_for_qualification",
    "future_selector_acceptance_of_disclosed_artifact",
    "malformed_role_manifests_accepted",
    "historical_false_disclosure_token_count",
    "unblocked_genuine_disclosure_mutations",
    "caller_removable_derived_secrets",
    "unknown_artifact_roles_accepted",
    "frozen_code_mutation_count",
    "platform_independent_difference_count",
)


def evaluate_m336a_readiness(values: dict) -> M336AReadinessGate:
    expected = {
        *_BOOLEAN_CRITERIA,
        *_ZERO_CRITERIA,
        "selector_invocation_count_after_qualification",
        "denied_coordinate_count",
        "denied_archive_hash_count",
        "new_untouched_corpus_acquired",
    }
    if set(values) != expected:
        raise ValueError(
            "M-33.6a readiness evidence field set is incomplete or substituted"
        )
    criteria = []
    criteria.extend((name, values[name] is True) for name in _BOOLEAN_CRITERIA)
    criteria.extend(
        (name, type(values[name]) is int and values[name] == 0)
        for name in _ZERO_CRITERIA
    )
    criteria.extend(
        (
            (
                "selector_invocation_count_after_qualification",
                values["selector_invocation_count_after_qualification"] == 1,
            ),
            ("denied_coordinate_count", values["denied_coordinate_count"] == 3),
            ("denied_archive_hash_count", values["denied_archive_hash_count"] == 3),
            (
                "new_untouched_corpus_acquired",
                values["new_untouched_corpus_acquired"] is False,
            ),
        )
    )
    result = tuple(criteria)
    failed = tuple(name for name, passed in result if not passed)
    body = {
        "criteria": result,
        "pass_count": sum(passed for _, passed in result),
        "mandatory_count": len(result),
        "failed_criteria": failed,
        "decision": M336AReadinessDecision.READY_FOR_FRESH_JAVA_FREEZE_V2
        if not failed
        else M336AReadinessDecision.BLOCKED,
    }
    return M336AReadinessGate(**body, gate_hash=content_hash(body))
