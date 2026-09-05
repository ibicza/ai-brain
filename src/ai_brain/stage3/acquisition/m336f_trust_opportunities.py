"""Evaluator-only, public-safe classification of disclosed false negatives."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash


@dataclass(frozen=True)
class TrustCoverageOpportunity:
    proposal_id: str | None
    declaration_identity_hash: str
    source_unit_identity: str
    production_blocker_reason: str
    opportunity_class: str
    compiler_report_hash: str | None
    production_decision_hash: str | None
    row_hash: str


@dataclass(frozen=True)
class TrustCoverageOpportunityReport:
    schema_version: int
    evaluation_only: bool
    expected_supported_count: int
    false_negative_opportunity_count: int
    category_counts: tuple[tuple[str, int], ...]
    rows: tuple[TrustCoverageOpportunity, ...]
    report_hash: str


def build_trust_coverage_opportunity_report(
    sealed_production: dict,
    golden_manifest,
) -> TrustCoverageOpportunityReport:
    """Compare disclosed evaluator support with already-sealed production decisions."""

    candidates = {
        _location_key(item): item for item in sealed_production["candidate_rows"]
    }
    rows = []
    expected_supported_count = 0
    for golden in golden_manifest.goldens:
        if not golden.expected_supported:
            continue
        expected_supported_count += 1
        candidate = candidates.get(_location_key(golden))
        if candidate is not None and candidate["production_trust_state"] == "trusted":
            continue
        blocker = (
            candidate.get("production_blocker_reason")
            if candidate is not None
            else "untrusted_missing_production_candidate"
        ) or "untrusted_other"
        body = {
            "proposal_id": candidate.get("proposal_id") if candidate else None,
            "declaration_identity_hash": (
                candidate["declaration_hash"] if candidate else golden.golden_hash
            ),
            "source_unit_identity": content_hash(
                (golden.source_unit_id, golden.document_bytes_hash)
            ),
            "production_blocker_reason": blocker,
            "opportunity_class": classify_trust_coverage_blocker(blocker),
            "compiler_report_hash": (
                candidate.get("compiler_report_hash") if candidate else None
            ),
            "production_decision_hash": (
                candidate.get("decision_hash") if candidate else None
            ),
        }
        rows.append(TrustCoverageOpportunity(**body, row_hash=content_hash(body)))
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                item.source_unit_identity,
                item.declaration_identity_hash,
                item.proposal_id or "",
            ),
        )
    )
    body = {
        "schema_version": 1,
        "evaluation_only": True,
        "expected_supported_count": expected_supported_count,
        "false_negative_opportunity_count": len(ordered),
        "category_counts": tuple(
            sorted(Counter(item.opportunity_class for item in ordered).items())
        ),
        "rows": ordered,
    }
    report = TrustCoverageOpportunityReport(**body, report_hash=content_hash(body))
    verify_trust_coverage_opportunity_report(report)
    return report


def classify_trust_coverage_blocker(blocker: str) -> str:
    normalized = blocker.casefold()
    rules = (
        ("missing_internal_source_closure", "MISSING_INTERNAL_SOURCE_CLOSURE"),
        ("available_internal_type", "UNRESOLVED_BUT_AVAILABLE_INTERNAL_TYPE"),
        ("missing_production_candidate", "UNSUPPORTED_DECLARATION_MAPPING"),
        ("unsupported", "UNSUPPORTED_DECLARATION_MAPPING"),
        ("field_evidence", "INCOMPLETE_FIELD_EVIDENCE"),
        ("packability", "PACKABILITY_FALSE_NEGATIVE"),
        ("classpath", "CLASSPATH_FALSE_NEGATIVE"),
        ("conflict", "CONFLICT_FALSE_POSITIVE"),
        ("compiler", "COMPILER_DIAGNOSTIC_OVERREACH"),
        ("resolution", "EXACT_TYPE_RESOLUTION_FALSE_NEGATIVE"),
        ("unresolved", "EXACT_TYPE_RESOLUTION_FALSE_NEGATIVE"),
    )
    return next((result for token, result in rules if token in normalized), "OTHER")


def verify_trust_coverage_opportunity_report(
    report: TrustCoverageOpportunityReport,
) -> None:
    for row in report.rows:
        body = asdict(row)
        claimed = body.pop("row_hash")
        if content_hash(
            body
        ) != claimed or row.opportunity_class != classify_trust_coverage_blocker(
            row.production_blocker_reason
        ):
            raise ValueError("trust coverage opportunity row mismatch")
    expected_categories = tuple(
        sorted(Counter(item.opportunity_class for item in report.rows).items())
    )
    body = asdict(report)
    claimed = body.pop("report_hash")
    if (
        report.schema_version != 1
        or report.evaluation_only is not True
        or report.false_negative_opportunity_count != len(report.rows)
        or report.category_counts != expected_categories
        or content_hash(body) != claimed
    ):
        raise ValueError("trust coverage opportunity report mismatch")


def _location_key(item) -> tuple[str, str, int, int]:
    def value(name):
        return item[name] if isinstance(item, dict) else getattr(item, name)

    return (
        value("document_bytes_hash"),
        value("source_unit_id"),
        value("start_offset"),
        value("end_offset"),
    )
