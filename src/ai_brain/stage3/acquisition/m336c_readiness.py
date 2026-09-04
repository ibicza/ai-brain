"""Hash-bound independent M-33.6c readiness recomputation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash


class M336CReadinessDecision(StrEnum):
    READY_FOR_FRESH_JAVA_FREEZE_V3 = "READY_FOR_FRESH_JAVA_FREEZE_V3"
    SAFE_CONSERVATIVE_SUBSET = "SAFE_CONSERVATIVE_SUBSET"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class M336CRawReport:
    schema_version: int
    report_type: str
    data: dict
    report_hash: str


@dataclass(frozen=True)
class M336CReadinessCriterion:
    name: str
    report_types: tuple[str, ...]
    observed: str
    passed: bool


@dataclass(frozen=True)
class M336CReadinessGate:
    schema_version: int
    raw_report_hashes: tuple[tuple[str, str], ...]
    criteria: tuple[M336CReadinessCriterion, ...]
    pass_count: int
    mandatory_count: int
    failed_criteria: tuple[str, ...]
    publication_eligible_root_count: int
    decision: M336CReadinessDecision
    gate_hash: str


_REPORT_FIELDS = {
    "license_matching": frozenset(
        {
            "precision",
            "false_apache_matches",
            "optional_variants_rejected",
            "true_conflict_mutations",
            "true_conflict_mutations_blocked",
        }
    ),
    "evidence_fusion": frozenset(
        {"old_conflicts", "classified_old_conflicts", "false_candidate_conflicts"}
    ),
    "document_roles": frozenset({"document_count", "unresolved_role_count"}),
    "source_use": frozenset(
        {
            "authority_axes_separate",
            "local_does_not_imply_publication",
            "scope_semantic_hash_equal",
            "model_created_approvals_accepted",
        }
    ),
    "candidate_qualification": frozenset(
        {
            "candidate_count",
            "typed_candidate_count",
            "analysis_eligible_root_count",
            "publication_eligible_root_count",
            "candidate_specific_branch_count",
        }
    ),
    "selector": frozenset({"invocation_count", "rerun_count"}),
    "java_production": frozenset(
        {
            "completed",
            "proposal_count",
            "post_trust_pack_failures",
            "evaluator_dependency_count",
            "golden_read_count",
        }
    ),
    "candidate_replay": frozenset({"compiled", "replay_without_evaluator"}),
    "evaluator": frozenset(
        {
            "ran_after_production_seal",
            "location_precision",
            "location_recall",
            "semantic_precision",
            "semantic_recall",
            "trust_precision",
            "trust_coverage",
            "wrong_trusted_count",
            "field_evidence_exactness",
            "resolution_agreement",
        }
    ),
    "runtime": frozenset({"installed", "runtime_queries_pass", "no_network"}),
    "artifact_contract": frozenset(
        {
            "h17_unknown_paths",
            "h17_unclassified_fields",
            "h17_missing_fields",
            "h17_unexpected_fields",
            "h17_role_mismatches",
            "hypothetical_unknown_paths",
            "hypothetical_missing_roles",
            "hypothetical_missing_fields",
            "hypothetical_extra_fields",
            "disclosure_claim_mismatches",
        }
    ),
    "disclosure_mutations": frozenset(
        {"mutation_count", "rejected_count", "accepted_count"}
    ),
    "formatting_tests": frozenset(
        {
            "ruff_format",
            "ruff_lint",
            "windows_suite",
            "karina_suite",
            "windows_clean",
            "karina_clean",
            "branch_upstream_equal",
            "new_untouched_corpus_acquired",
        }
    ),
    "cross_platform": frozenset({"platform_independent_difference_count"}),
}


def build_m336c_raw_report(report_type: str, data: dict) -> M336CRawReport:
    expected = _REPORT_FIELDS.get(report_type)
    if expected is None or set(data) != expected:
        raise ValueError("M-33.6c raw report schema is incomplete or substituted")
    body = {"schema_version": 1, "report_type": report_type, "data": data}
    return M336CRawReport(**body, report_hash=content_hash(body))


def verify_m336c_raw_report(report: M336CRawReport) -> None:
    rebuilt = build_m336c_raw_report(report.report_type, report.data)
    if report.schema_version != 1 or rebuilt.report_hash != report.report_hash:
        raise ValueError("M-33.6c raw report hash mismatch")


def evaluate_m336c_readiness(
    reports: tuple[M336CRawReport, ...],
) -> M336CReadinessGate:
    if len(reports) != len(_REPORT_FIELDS):
        raise ValueError("M-33.6c raw report denominator mismatch")
    by_type = {}
    for report in reports:
        verify_m336c_raw_report(report)
        if report.report_type in by_type:
            raise ValueError("duplicate M-33.6c raw report type")
        by_type[report.report_type] = report
    if set(by_type) != set(_REPORT_FIELDS):
        raise ValueError("missing M-33.6c mandatory raw report")
    data = {name: value.data for name, value in by_type.items()}
    criteria = []

    def criterion(name, report_types, observed, passed):
        criteria.append(
            M336CReadinessCriterion(
                name, tuple(report_types), str(observed), bool(passed)
            )
        )

    license_data = data["license_matching"]
    fusion = data["evidence_fusion"]
    roles = data["document_roles"]
    criterion(
        "license_precision",
        ("license_matching",),
        license_data["precision"],
        license_data["precision"] == "1.000000",
    )
    criterion(
        "false_apache_matches",
        ("license_matching",),
        license_data["false_apache_matches"],
        license_data["false_apache_matches"] == 0,
    )
    criterion(
        "optional_variants_rejected",
        ("license_matching",),
        license_data["optional_variants_rejected"],
        license_data["optional_variants_rejected"] == 0,
    )
    criterion(
        "old_conflicts_classified",
        ("evidence_fusion",),
        f"{fusion['classified_old_conflicts']}/{fusion['old_conflicts']}",
        fusion["old_conflicts"] > 0
        and fusion["classified_old_conflicts"] == fusion["old_conflicts"],
    )
    criterion(
        "false_candidate_conflicts",
        ("evidence_fusion",),
        fusion["false_candidate_conflicts"],
        fusion["false_candidate_conflicts"] == 0,
    )
    criterion(
        "true_conflict_mutations_blocked",
        ("license_matching",),
        f"{license_data['true_conflict_mutations_blocked']}/{license_data['true_conflict_mutations']}",
        license_data["true_conflict_mutations"] > 0
        and license_data["true_conflict_mutations_blocked"]
        == license_data["true_conflict_mutations"],
    )
    criterion(
        "unresolved_document_roles",
        ("document_roles",),
        roles["unresolved_role_count"],
        roles["document_count"] > 0 and roles["unresolved_role_count"] == 0,
    )

    authority = data["source_use"]
    for name in (
        "authority_axes_separate",
        "local_does_not_imply_publication",
        "scope_semantic_hash_equal",
    ):
        criterion(name, ("source_use",), authority[name], authority[name] is True)
    criterion(
        "model_created_approvals_accepted",
        ("source_use",),
        authority["model_created_approvals_accepted"],
        authority["model_created_approvals_accepted"] == 0,
    )

    candidates = data["candidate_qualification"]
    selector = data["selector"]
    criterion(
        "analysis_eligible_roots",
        ("candidate_qualification",),
        candidates["analysis_eligible_root_count"],
        candidates["analysis_eligible_root_count"] >= 4,
    )
    criterion(
        "typed_candidate_decisions",
        ("candidate_qualification",),
        f"{candidates['typed_candidate_count']}/{candidates['candidate_count']}",
        candidates["candidate_count"] > 0
        and candidates["typed_candidate_count"] == candidates["candidate_count"],
    )
    criterion(
        "selector_invocation",
        ("selector",),
        selector["invocation_count"],
        selector["invocation_count"] == 1,
    )
    criterion(
        "selector_rerun",
        ("selector",),
        selector["rerun_count"],
        selector["rerun_count"] == 0,
    )
    criterion(
        "candidate_specific_branches",
        ("candidate_qualification",),
        candidates["candidate_specific_branch_count"],
        candidates["candidate_specific_branch_count"] == 0,
    )

    production = data["java_production"]
    replay = data["candidate_replay"]
    evaluator = data["evaluator"]
    runtime = data["runtime"]
    criterion(
        "production_completed",
        ("java_production",),
        production["completed"],
        production["completed"] is True,
    )
    criterion(
        "candidate_pack_compiled",
        ("candidate_replay",),
        replay["compiled"],
        replay["compiled"] is True,
    )
    criterion(
        "candidate_replay_without_evaluator",
        ("candidate_replay",),
        replay["replay_without_evaluator"],
        replay["replay_without_evaluator"] is True,
    )
    criterion(
        "evaluator_after_seal",
        ("evaluator",),
        evaluator["ran_after_production_seal"],
        evaluator["ran_after_production_seal"] is True,
    )
    criterion(
        "wrong_trusted",
        ("evaluator",),
        evaluator["wrong_trusted_count"],
        evaluator["wrong_trusted_count"] == 0,
    )
    for name, threshold in (
        ("location_precision", 1.0),
        ("location_recall", 0.95),
        ("semantic_precision", 1.0),
        ("semantic_recall", 0.95),
        ("trust_precision", 1.0),
        ("trust_coverage", 0.8),
        ("field_evidence_exactness", 1.0),
        ("resolution_agreement", 1.0),
    ):
        observed = _ratio(evaluator[name])
        criterion(name, ("evaluator",), f"{observed:.6f}", observed >= threshold)
    criterion(
        "post_trust_pack_failures",
        ("java_production",),
        production["post_trust_pack_failures"],
        production["post_trust_pack_failures"] == 0,
    )
    criterion(
        "production_evaluator_dependencies",
        ("java_production",),
        production["evaluator_dependency_count"],
        production["evaluator_dependency_count"] == 0,
    )
    criterion(
        "production_golden_reads",
        ("java_production",),
        production["golden_read_count"],
        production["golden_read_count"] == 0,
    )
    criterion(
        "runtime_installed",
        ("runtime",),
        runtime["installed"],
        runtime["installed"] is True,
    )
    criterion(
        "runtime_queries",
        ("runtime",),
        runtime["runtime_queries_pass"],
        runtime["runtime_queries_pass"] is True,
    )
    criterion(
        "runtime_no_network",
        ("runtime",),
        runtime["no_network"],
        runtime["no_network"] is True,
    )

    contract = data["artifact_contract"]
    for name in contract:
        criterion(name, ("artifact_contract",), contract[name], contract[name] == 0)
    mutations = data["disclosure_mutations"]
    criterion(
        "contract_mutations",
        ("disclosure_mutations",),
        f"{mutations['rejected_count']}/{mutations['mutation_count']}",
        mutations["mutation_count"] >= 1000
        and mutations["accepted_count"] == 0
        and mutations["rejected_count"] == mutations["mutation_count"],
    )
    differences = data["cross_platform"]["platform_independent_difference_count"]
    criterion(
        "cross_platform_differences", ("cross_platform",), differences, differences == 0
    )

    quality = data["formatting_tests"]
    for name in (
        "ruff_format",
        "ruff_lint",
        "windows_suite",
        "karina_suite",
        "windows_clean",
        "karina_clean",
        "branch_upstream_equal",
    ):
        criterion(name, ("formatting_tests",), quality[name], quality[name] is True)
    criterion(
        "no_new_untouched_corpus",
        ("formatting_tests",),
        quality["new_untouched_corpus_acquired"],
        quality["new_untouched_corpus_acquired"] is False,
    )

    result = tuple(criteria)
    failed = tuple(item.name for item in result if not item.passed)
    publication_count = candidates["publication_eligible_root_count"]
    if failed:
        decision = M336CReadinessDecision.BLOCKED
    elif publication_count < 4:
        decision = M336CReadinessDecision.SAFE_CONSERVATIVE_SUBSET
    else:
        decision = M336CReadinessDecision.READY_FOR_FRESH_JAVA_FREEZE_V3
    body = {
        "schema_version": 1,
        "raw_report_hashes": tuple(
            sorted((name, report.report_hash) for name, report in by_type.items())
        ),
        "criteria": result,
        "pass_count": sum(item.passed for item in result),
        "mandatory_count": len(result),
        "failed_criteria": failed,
        "publication_eligible_root_count": publication_count,
        "decision": decision,
    }
    return M336CReadinessGate(**body, gate_hash=content_hash(body))


def verify_m336c_readiness(
    reports: tuple[M336CRawReport, ...], claimed: M336CReadinessGate
) -> None:
    recomputed = evaluate_m336c_readiness(reports)
    if recomputed != claimed:
        raise ValueError(
            "M-33.6c readiness counters, ratios, criteria, or decision differ"
        )


def _ratio(value) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("readiness ratio is not numeric") from exc
    if not 0.0 <= result <= 1.0:
        raise ValueError("readiness ratio is outside [0,1]")
    return result
