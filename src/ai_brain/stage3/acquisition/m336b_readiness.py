"""Independently recomputed M-33.6b pre-F17 readiness gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash


class M336BPreFreezeDecision(StrEnum):
    READY_TO_CREATE_F17 = "READY_TO_CREATE_F17"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class M336BReadinessCriterion:
    name: str
    evidence_artifact: str
    evidence_fields: tuple[str, ...]
    passed: bool


@dataclass(frozen=True)
class M336BPreFreezeGate:
    schema_version: int
    evidence_report_hashes: tuple[tuple[str, str], ...]
    criteria: tuple[M336BReadinessCriterion, ...]
    pass_count: int
    mandatory_count: int
    failed_criteria: tuple[str, ...]
    decision: M336BPreFreezeDecision
    gate_hash: str


_REQUIRED_REPORTS = (
    "windows_rehearsal",
    "karina_rehearsal",
    "platform_comparison",
    "windows_quality",
    "karina_quality",
    "source_access_audit",
)


def verify_hashed_raw_report(report: dict) -> None:
    if not isinstance(report, dict) or "report_hash" not in report:
        raise ValueError("readiness evidence is not a hashed raw report")
    body = dict(report)
    claimed = body.pop("report_hash")
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise ValueError("readiness raw report hash mismatch")


def evaluate_m336b_pre_freeze_gate(reports: dict[str, dict]) -> M336BPreFreezeGate:
    """Load raw mechanism reports and derive every mandatory criterion."""

    if tuple(sorted(reports)) != tuple(sorted(_REQUIRED_REPORTS)):
        raise ValueError("M-33.6b readiness evidence set is incomplete or substituted")
    for report in reports.values():
        verify_hashed_raw_report(report)

    windows = reports["windows_rehearsal"]
    karina = reports["karina_rehearsal"]
    comparison = reports["platform_comparison"]
    quality_reports = (reports["windows_quality"], reports["karina_quality"])
    access = reports["source_access_audit"]
    evidence_hashes = tuple(
        (name, reports[name]["report_hash"]) for name in _REQUIRED_REPORTS
    )

    def criterion(name, artifact, fields, passed):
        return M336BReadinessCriterion(name, artifact, tuple(fields), bool(passed))

    rehearsal_ok = lambda report: report["status"] == "PASS"
    criteria = (
        criterion(
            "provenance_envelope_v2_strict_replay",
            "windows_rehearsal",
            ("candidate_count", "envelope_replay_pass_count"),
            windows["candidate_count"] > 0
            and windows["candidate_count"] == windows["envelope_replay_pass_count"],
        ),
        criterion(
            "actual_scm_ref_commit_verification",
            "windows_rehearsal",
            ("candidate_count", "scm_receipt_verified_count"),
            windows["scm_receipt_verified_count"] == windows["candidate_count"],
        ),
        criterion(
            "authenticity_fallback_consistency",
            "windows_rehearsal",
            ("strong_authenticity_count", "no_sidecar_eligible_count"),
            windows["strong_authenticity_count"] == windows["candidate_count"]
            and windows["no_sidecar_eligible_count"] >= 2,
        ),
        criterion(
            "no_unverified_signature_authority",
            "windows_rehearsal",
            (
                "present_unverified_signature_count",
                "unverified_signature_authority_count",
            ),
            windows["present_unverified_signature_count"] > 0
            and windows["unverified_signature_authority_count"] == 0,
        ),
        criterion(
            "correspondence_v2",
            "windows_rehearsal",
            (
                "correspondence_eligible_count",
                "correspondence_unmatched_count",
                "correspondence_ambiguous_count",
            ),
            windows["correspondence_eligible_count"] > 0
            and windows["correspondence_unmatched_count"] == 0
            and windows["correspondence_ambiguous_count"] == 0,
        ),
        criterion(
            "qualification_one_to_one_closure",
            "windows_rehearsal",
            ("qualification_status", "candidate_count"),
            windows["qualification_status"] == "READY_FOR_SINGLE_SELECTION"
            and windows["candidate_count"] == 3,
        ),
        criterion(
            "distinct_eligible_roots",
            "windows_rehearsal",
            ("distinct_eligible_root_count",),
            windows["distinct_eligible_root_count"] == 3,
        ),
        criterion(
            "disclosed_registry_append_replay",
            "windows_rehearsal",
            ("registry_entry_count", "registry_manifest_hash"),
            windows["registry_entry_count"] == windows["candidate_count"]
            and _sha256(windows["registry_manifest_hash"]),
        ),
        criterion(
            "all_denylist_identity_classes_enforced",
            "windows_rehearsal",
            ("denylist_identity_class_count", "denylist_identity_class_block_count"),
            windows["denylist_identity_class_count"] == 11
            and windows["denylist_identity_class_block_count"] == 11,
        ),
        criterion(
            "mandatory_disclosure_claims_complete",
            "windows_rehearsal",
            (
                "disclosure_required_claim_count",
                "disclosure_extracted_claim_count",
                "disclosure_missing_claim_count",
                "disclosure_extra_claim_count",
            ),
            windows["disclosure_required_claim_count"] > 0
            and windows["disclosure_extracted_claim_count"]
            == windows["disclosure_required_claim_count"]
            and windows["disclosure_missing_claim_count"] == 0
            and windows["disclosure_extra_claim_count"] == 0,
        ),
        criterion(
            "readiness_values_independently_recomputed",
            "pre_freeze_gate",
            ("evidence_report_hashes", "criteria"),
            len(evidence_hashes) == len(_REQUIRED_REPORTS)
            and all(_sha256(value) for _name, value in evidence_hashes),
        ),
        criterion(
            "disclosed_corpus_exact_production_rehearsal",
            "windows_rehearsal",
            (
                "status",
                "production_entry_point",
                "hardcoded_immutable_scm_boolean_count",
                "production_development_mechanism_difference_count",
            ),
            rehearsal_ok(windows)
            and windows["production_entry_point"]
            == "acquire_and_qualify_maven_source_candidates"
            and windows["hardcoded_immutable_scm_boolean_count"] == 0
            and windows["production_development_mechanism_difference_count"] == 0,
        ),
        criterion(
            "windows_karina_deterministic_rehearsal",
            "platform_comparison",
            ("difference_count", "status"),
            rehearsal_ok(karina)
            and comparison["difference_count"] == 0
            and comparison["status"] == "PASS",
        ),
        criterion(
            "prior_java_semantic_trust_regressions",
            "windows_quality+karina_quality",
            ("targeted_pass", "no_torch_network_pass"),
            all(
                item["targeted_pass"] and item["no_torch_network_pass"]
                for item in quality_reports
            ),
        ),
        criterion(
            "ruff_full_tests",
            "windows_quality+karina_quality",
            ("ruff_pass", "full_suite_pass"),
            all(
                item["ruff_pass"] and item["full_suite_pass"]
                for item in quality_reports
            ),
        ),
        criterion(
            "no_fresh_source_body_before_f17",
            "source_access_audit",
            (
                "fresh_source_jar_get_count",
                "fresh_source_tree_body_get_count",
                "fresh_java_body_inspection_count",
            ),
            access["fresh_source_jar_get_count"] == 0
            and access["fresh_source_tree_body_get_count"] == 0
            and access["fresh_java_body_inspection_count"] == 0,
        ),
    )
    failed = tuple(item.name for item in criteria if not item.passed)
    body = {
        "schema_version": 1,
        "evidence_report_hashes": evidence_hashes,
        "criteria": criteria,
        "pass_count": sum(item.passed for item in criteria),
        "mandatory_count": len(criteria),
        "failed_criteria": failed,
        "decision": M336BPreFreezeDecision.READY_TO_CREATE_F17
        if not failed
        else M336BPreFreezeDecision.BLOCKED,
    }
    return M336BPreFreezeGate(**body, gate_hash=content_hash(body))


def _sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
