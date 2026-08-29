"""Fail-closed proposal trust state machine and field-evidence gates."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum, StrEnum

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.identity import (
    CanonicalSemanticIdentity,
    IdentityBlocker,
    IdentityMatch,
    JavaLocationMatch,
    PrecompilerIdentityReport,
    detect_precompiler_identity_conflicts,
    match_java_source_location,
    parse_java_source_identities,
    verify_semantic_identity,
)
from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    KnowledgeProposal,
    SourceBundle,
    SourceLocation,
    SourceSegment,
)
from ai_brain.stage3.acquisition.segmentation import (
    SegmentDeduplicationReport,
    require_unique_segments,
    verify_segments,
    with_proposal_counts,
)
from ai_brain.stage3.acquisition.sources import verify_bundle

TRUST_CHECKER_VERSION = "m34.semantic-location-trust.v1"


class ProposalTrustState(StrEnum):
    CANDIDATE = "candidate"
    SOURCE_EVIDENCE_FOUND = "source_evidence_found"
    IDENTITY_RESOLVED = "identity_resolved"
    GOLDEN_LOCATION_MATCHED = "golden_location_matched"
    TRUSTED = "trusted"
    WITHHELD = "withheld"
    ABSTAINED = "abstained"
    REJECTED = "rejected"


class TrustBlockerReason(StrEnum):
    LOCATION_MISMATCH = "untrusted_location_mismatch"
    AMBIGUOUS_IDENTITY = "untrusted_ambiguous_identity"
    MISSING_FIELD_EVIDENCE = "untrusted_missing_field_evidence"
    DUPLICATE_SEGMENT = "untrusted_duplicate_segment"
    CONFLICTING_IDENTITY = "untrusted_conflicting_identity"
    MISSING_IDENTITY = "untrusted_missing_identity"
    GOLDEN_REQUIRED = "untrusted_golden_location_required"


class EvidenceFailureCategory(StrEnum):
    EXTRACTION_FAILURE = "extraction_failure"
    SEGMENTATION_LOSS = "segmentation_loss"
    SYMBOL_PARSE_FAILURE = "symbol_parse_failure"
    MATCHER_FAILURE = "matcher_failure"


@dataclass(frozen=True)
class FieldSourceEvidence:
    proposal_id: str
    field_path: str
    document_id: str
    document_bytes_hash: str
    source_location: SourceLocation
    source_bytes_hash: str
    raw_text: str
    normalized_value: str
    transformation_id: str
    transformation_hash: str
    extraction_method: ExtractionMethod
    semantic_identity_hash: str
    evidence_hash: str


@dataclass(frozen=True)
class MissingFieldEvidence:
    proposal_id: str
    field_path: str
    document_id: str | None
    source_line: int | None
    failure_category: EvidenceFailureCategory
    missing_hash: str


@dataclass(frozen=True)
class FieldEvidenceCompletenessReport:
    domain: str
    required_count: int
    evidence_count: int
    completeness_ratio: str
    status: str
    missing: tuple[MissingFieldEvidence, ...]
    report_hash: str


@dataclass(frozen=True)
class TrustTransitionReceipt:
    proposal_id: str
    previous_state: ProposalTrustState
    next_state: ProposalTrustState
    reason: str
    source_document_hash: str
    semantic_identity_hash: str | None
    source_span_hash: str | None
    checker_version: str
    deterministic_run_id: str
    receipt_hash: str


@dataclass(frozen=True)
class ProposalTrustDecision:
    proposal_id: str
    final_state: ProposalTrustState
    blocker_reason: TrustBlockerReason | None
    identity_match: IdentityMatch
    semantic_identity_hash: str | None
    receipts: tuple[TrustTransitionReceipt, ...]
    decision_hash: str


@dataclass(frozen=True)
class ProposalTrustGateReport:
    domain: str
    status: str
    trusted_without_golden_allowed: bool
    proposal_count: int
    trusted_count: int
    withheld_count: int
    rejected_count: int
    blocker_counts: tuple[tuple[str, int], ...]
    trusted_proposal_ids: tuple[str, ...]
    decisions: tuple[ProposalTrustDecision, ...]
    field_evidence: FieldEvidenceCompletenessReport
    segmentation: SegmentDeduplicationReport
    precompiler: PrecompilerIdentityReport
    duplicate_derived_trusted_proposals: int
    report_hash: str


def make_field_evidence(
    *,
    proposal: KnowledgeProposal,
    field_path: str,
    document_id: str,
    document_bytes_hash: str,
    source_location: SourceLocation,
    raw: bytes,
    normalized_value: str,
    semantic_identity_hash: str,
    transformation_id: str = "m34.exact-source-field.v1",
) -> FieldSourceEvidence:
    span = raw[source_location.byte_start : source_location.byte_end]
    values = {
        "proposal_id": proposal.proposal_id,
        "field_path": field_path,
        "document_id": document_id,
        "document_bytes_hash": document_bytes_hash,
        "source_location": source_location,
        "source_bytes_hash": bytes_hash(span),
        "raw_text": span.decode("utf-8", errors="strict"),
        "normalized_value": normalized_value,
        "transformation_id": transformation_id,
        "transformation_hash": content_hash({"transformation_id": transformation_id}),
        "extraction_method": proposal.extraction_method,
        "semantic_identity_hash": semantic_identity_hash,
    }
    return FieldSourceEvidence(**values, evidence_hash=content_hash(values))


def required_field_values(proposal: KnowledgeProposal) -> tuple[tuple[str, str], ...]:
    return tuple(_leaves("content", proposal.proposed_content)) + tuple(
        _leaves("applicability", proposal.proposed_applicability)
    )


def evaluate_field_evidence_completeness(
    *,
    domain: str,
    proposals: tuple[KnowledgeProposal, ...],
    evidence: tuple[FieldSourceEvidence, ...],
    identities: dict[str, CanonicalSemanticIdentity],
    documents: dict[str, bytes],
    required_fields: dict[str, tuple[str, ...]] | None = None,
    failure_categories: dict[tuple[str, str], EvidenceFailureCategory] | None = None,
) -> FieldEvidenceCompletenessReport:
    proposal_by_id = {item.proposal_id: item for item in proposals}
    expected_values = {
        proposal.proposal_id: dict(required_field_values(proposal))
        for proposal in proposals
    }
    required = {
        proposal.proposal_id: (
            required_fields[proposal.proposal_id]
            if required_fields and proposal.proposal_id in required_fields
            else tuple(sorted(expected_values[proposal.proposal_id]))
        )
        for proposal in proposals
    }
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        key = (item.proposal_id, item.field_path)
        if key in seen:
            raise ValueError("duplicate field source evidence")
        seen.add(key)
        proposal = proposal_by_id.get(item.proposal_id)
        identity = identities.get(item.proposal_id)
        raw = documents.get(item.document_id)
        if proposal is None or identity is None or raw is None:
            raise ValueError("field evidence source closure is invalid")
        verify_semantic_identity(identity)
        if (
            item.document_bytes_hash != identity.source_snapshot_hash
            or bytes_hash(raw) != item.document_bytes_hash
            or item.semantic_identity_hash != identity.identity_hash
            or item.field_path not in required[item.proposal_id]
        ):
            raise ValueError("field evidence identity closure is invalid")
        expected = expected_values[item.proposal_id].get(item.field_path)
        if expected is not None and expected != item.normalized_value:
            raise ValueError("field evidence normalized value mismatch")
        location = item.source_location
        if not 0 <= location.byte_start < location.byte_end <= len(raw):
            raise ValueError("field evidence source range is invalid")
        span = raw[location.byte_start : location.byte_end]
        body = asdict(item)
        claimed = body.pop("evidence_hash")
        if (
            bytes_hash(span) != item.source_bytes_hash
            or span.decode("utf-8", errors="strict") != item.raw_text
            or content_hash(body) != claimed
            or item.transformation_hash
            != content_hash({"transformation_id": item.transformation_id})
        ):
            raise ValueError("field evidence cannot dereference exact source bytes")
    required_keys = {
        (proposal_id, field_path)
        for proposal_id, paths in required.items()
        for field_path in paths
    }
    missing = []
    categories = failure_categories or {}
    for proposal_id, field_path in sorted(required_keys - seen):
        identity = identities.get(proposal_id)
        values = {
            "proposal_id": proposal_id,
            "field_path": field_path,
            "document_id": identity.source_document_id if identity else None,
            "source_line": identity.start_line if identity else None,
            "failure_category": categories.get(
                (proposal_id, field_path),
                EvidenceFailureCategory.EXTRACTION_FAILURE
                if identity
                else EvidenceFailureCategory.SYMBOL_PARSE_FAILURE,
            ),
        }
        missing.append(
            MissingFieldEvidence(**values, missing_hash=content_hash(values))
        )
    required_count = len(required_keys)
    evidence_count = len(required_keys & seen)
    body = {
        "domain": domain,
        "required_count": required_count,
        "evidence_count": evidence_count,
        "completeness_ratio": _rate(evidence_count, required_count),
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "missing": tuple(missing),
    }
    return FieldEvidenceCompletenessReport(**body, report_hash=content_hash(body))


def evaluate_proposal_trust_gate(
    *,
    domain: str,
    bundle: SourceBundle,
    segments: tuple[SourceSegment, ...],
    proposals: tuple[KnowledgeProposal, ...],
    proposal_identities: dict[str, CanonicalSemanticIdentity],
    source_identities: tuple[CanonicalSemanticIdentity, ...],
    golden_identities: dict[str, CanonicalSemanticIdentity],
    field_evidence: tuple[FieldSourceEvidence, ...],
    store,
    deterministic_run_id: str,
    trusted_without_golden_allowed: bool = False,
    required_fields: dict[str, tuple[str, ...]] | None = None,
    failure_categories: dict[tuple[str, str], EvidenceFailureCategory] | None = None,
) -> ProposalTrustGateReport:
    verify_bundle(bundle, store=store)
    verify_segments(bundle, segments, store)
    segment_ids = {item.segment_id for item in segments}
    for proposal in proposals:
        row = asdict(proposal)
        claimed = row.pop("proposal_hash")
        if (
            content_hash(row) != claimed
            or proposal.source_bundle_id != bundle.bundle_id
            or not set(proposal.segment_ids) <= segment_ids
        ):
            raise ValueError("proposal hash or source closure is invalid")
    segmentation = require_unique_segments(segments)
    documents = {
        item.document_id: store.get_blob(item.bytes_hash) for item in bundle.documents
    }
    java_requires_complete = domain.casefold() == "java"
    if java_requires_complete:
        parsed_source_identities = tuple(
            identity
            for document in bundle.documents
            for identity in parse_java_source_identities(
                document, documents[document.document_id]
            )
        )
        if tuple(item.identity_hash for item in source_identities) != tuple(
            item.identity_hash for item in parsed_source_identities
        ):
            raise ValueError("Java source identities do not match parsed source bytes")
        source_identities = parsed_source_identities
    completeness = evaluate_field_evidence_completeness(
        domain=domain,
        proposals=proposals,
        evidence=field_evidence,
        identities=proposal_identities,
        documents=documents,
        required_fields=required_fields,
        failure_categories=failure_categories,
    )
    identities = tuple(
        (proposal.proposal_id, proposal_identities[proposal.proposal_id])
        for proposal in proposals
        if proposal.proposal_id in proposal_identities
    )
    precompiler = detect_precompiler_identity_conflicts(identities)
    decisions = []
    for proposal in sorted(proposals, key=lambda item: item.proposal_id):
        identity = proposal_identities.get(proposal.proposal_id)
        golden = golden_identities.get(proposal.proposal_id)
        if java_requires_complete and completeness.status != "COMPLETE":
            decisions.append(
                _blocked_decision(
                    proposal,
                    identity,
                    TrustBlockerReason.MISSING_FIELD_EVIDENCE,
                    IdentityMatch.MISSING,
                    bundle,
                    deterministic_run_id,
                )
            )
            continue
        if precompiler.status != "PASS":
            decisions.append(
                _blocked_decision(
                    proposal,
                    identity,
                    TrustBlockerReason.CONFLICTING_IDENTITY,
                    IdentityMatch.CONFLICT,
                    bundle,
                    deterministic_run_id,
                )
            )
            continue
        if golden is None and not trusted_without_golden_allowed:
            decisions.append(
                _blocked_decision(
                    proposal,
                    identity,
                    TrustBlockerReason.GOLDEN_REQUIRED,
                    IdentityMatch.MISSING,
                    bundle,
                    deterministic_run_id,
                )
            )
            continue
        match = match_java_source_location(
            identity,
            source_identities,
            golden_identity=golden
            if golden is not None or not trusted_without_golden_allowed
            else identity,
        )
        if match.blocker_reason is not None:
            decisions.append(
                _blocked_decision(
                    proposal,
                    identity,
                    _trust_blocker(match),
                    match.status,
                    bundle,
                    deterministic_run_id,
                )
            )
            continue
        decisions.append(
            _trusted_decision(
                proposal,
                identity,
                match,
                bundle,
                deterministic_run_id,
            )
        )
    values = tuple(decisions)
    counts = Counter(
        item.blocker_reason.value for item in values if item.blocker_reason is not None
    )
    trusted = tuple(
        item.proposal_id
        for item in values
        if item.final_state is ProposalTrustState.TRUSTED
    )
    segmentation = with_proposal_counts(
        segmentation,
        before=len(proposals),
        after=len(proposals),
        trusted_blocked=sum(
            item.blocker_reason is TrustBlockerReason.DUPLICATE_SEGMENT
            for item in values
        ),
    )
    hard_failure = (
        precompiler.status != "PASS"
        or segmentation.status != "PASS"
        or (java_requires_complete and completeness.status != "COMPLETE")
    )
    body = {
        "domain": domain,
        "status": (
            "FAIL"
            if hard_failure
            else "PASS_WITH_WITHHELD"
            if len(trusted) != len(proposals)
            else "PASS"
        ),
        "trusted_without_golden_allowed": trusted_without_golden_allowed,
        "proposal_count": len(proposals),
        "trusted_count": len(trusted),
        "withheld_count": sum(
            item.final_state is ProposalTrustState.WITHHELD for item in values
        ),
        "rejected_count": sum(
            item.final_state is ProposalTrustState.REJECTED for item in values
        ),
        "blocker_counts": tuple(sorted(counts.items())),
        "trusted_proposal_ids": trusted,
        "decisions": values,
        "field_evidence": completeness,
        "segmentation": segmentation,
        "precompiler": precompiler,
        "duplicate_derived_trusted_proposals": 0,
    }
    return ProposalTrustGateReport(**body, report_hash=content_hash(body))


def verify_trust_gate_report(report: ProposalTrustGateReport) -> None:
    body = asdict(report)
    claimed = body.pop("report_hash")
    if content_hash(body) != claimed:
        raise ValueError("proposal trust gate report hash mismatch")
    if report.duplicate_derived_trusted_proposals:
        raise ValueError("duplicate-derived trusted proposals are forbidden")
    if report.domain.casefold() == "java" and (
        report.trusted_without_golden_allowed
        or (report.field_evidence.status != "COMPLETE" and report.trusted_count)
    ):
        raise ValueError("Java trust gate violated completeness or golden policy")
    for decision in report.decisions:
        _verify_decision(decision)


def _trusted_decision(proposal, identity, match, bundle, run_id):
    if identity is None:
        raise ValueError("trusted proposal lacks semantic identity")
    document_hash = _document_hash(bundle, identity.source_document_id)
    steps = (
        (ProposalTrustState.CANDIDATE, ProposalTrustState.SOURCE_EVIDENCE_FOUND),
        (
            ProposalTrustState.SOURCE_EVIDENCE_FOUND,
            ProposalTrustState.IDENTITY_RESOLVED,
        ),
        (
            ProposalTrustState.IDENTITY_RESOLVED,
            ProposalTrustState.GOLDEN_LOCATION_MATCHED,
        ),
        (
            ProposalTrustState.GOLDEN_LOCATION_MATCHED,
            ProposalTrustState.TRUSTED,
        ),
    )
    receipts = tuple(
        _receipt(
            proposal.proposal_id,
            previous,
            next_state,
            next_state.value,
            document_hash,
            identity,
            run_id,
        )
        for previous, next_state in steps
    )
    body = {
        "proposal_id": proposal.proposal_id,
        "final_state": ProposalTrustState.TRUSTED,
        "blocker_reason": None,
        "identity_match": match.status,
        "semantic_identity_hash": identity.identity_hash,
        "receipts": receipts,
    }
    return ProposalTrustDecision(**body, decision_hash=content_hash(body))


def _blocked_decision(proposal, identity, blocker, identity_match, bundle, run_id):
    document_hash = (
        _document_hash(bundle, identity.source_document_id)
        if identity
        else bundle.bundle_hash
    )
    receipt = _receipt(
        proposal.proposal_id,
        ProposalTrustState.CANDIDATE,
        ProposalTrustState.WITHHELD,
        blocker.value,
        document_hash,
        identity,
        run_id,
    )
    body = {
        "proposal_id": proposal.proposal_id,
        "final_state": ProposalTrustState.WITHHELD,
        "blocker_reason": blocker,
        "identity_match": identity_match,
        "semantic_identity_hash": identity.identity_hash if identity else None,
        "receipts": (receipt,),
    }
    return ProposalTrustDecision(**body, decision_hash=content_hash(body))


def _receipt(
    proposal_id, previous, next_state, reason, document_hash, identity, run_id
):
    body = {
        "proposal_id": proposal_id,
        "previous_state": previous,
        "next_state": next_state,
        "reason": reason,
        "source_document_hash": document_hash,
        "semantic_identity_hash": identity.identity_hash if identity else None,
        "source_span_hash": identity.source_evidence_span_hash if identity else None,
        "checker_version": TRUST_CHECKER_VERSION,
        "deterministic_run_id": run_id,
    }
    return TrustTransitionReceipt(**body, receipt_hash=content_hash(body))


def _verify_decision(value):
    body = asdict(value)
    claimed = body.pop("decision_hash")
    if content_hash(body) != claimed:
        raise ValueError("proposal trust decision hash mismatch")
    previous = ProposalTrustState.CANDIDATE
    for receipt in value.receipts:
        row = asdict(receipt)
        receipt_hash = row.pop("receipt_hash")
        if content_hash(row) != receipt_hash or receipt.previous_state is not previous:
            raise ValueError("proposal trust transition receipt is invalid")
        previous = receipt.next_state
    if previous is not value.final_state:
        raise ValueError("proposal trust transition closure is incomplete")
    if value.final_state is ProposalTrustState.TRUSTED:
        expected = tuple(item.next_state for item in value.receipts)
        if expected != (
            ProposalTrustState.SOURCE_EVIDENCE_FOUND,
            ProposalTrustState.IDENTITY_RESOLVED,
            ProposalTrustState.GOLDEN_LOCATION_MATCHED,
            ProposalTrustState.TRUSTED,
        ):
            raise ValueError("proposal entered trusted through an illegal transition")


def _trust_blocker(match: JavaLocationMatch) -> TrustBlockerReason:
    mapping = {
        IdentityBlocker.LOCATION_MISMATCH: TrustBlockerReason.LOCATION_MISMATCH,
        IdentityBlocker.AMBIGUOUS_IDENTITY: TrustBlockerReason.AMBIGUOUS_IDENTITY,
        IdentityBlocker.DUPLICATE_SEGMENT: TrustBlockerReason.DUPLICATE_SEGMENT,
        IdentityBlocker.CONFLICTING_IDENTITY: TrustBlockerReason.CONFLICTING_IDENTITY,
        IdentityBlocker.MISSING_IDENTITY: TrustBlockerReason.MISSING_IDENTITY,
    }
    return mapping[match.blocker_reason]


def _document_hash(bundle, document_id):
    document = next(
        (item for item in bundle.documents if item.document_id == document_id), None
    )
    if document is None:
        raise ValueError("semantic identity document is outside source bundle")
    return document.bytes_hash


def _leaves(path: str, value):
    if is_dataclass(value):
        result = []
        for key, item in asdict(value).items():
            result.extend(_leaves(f"{path}.{key}", item))
        return result
    if isinstance(value, dict):
        result = []
        for key in sorted(value):
            result.extend(_leaves(f"{path}.{key}", value[key]))
        return result
    if isinstance(value, (tuple, list)):
        result = []
        for index, item in enumerate(value):
            result.extend(_leaves(f"{path}[{index}]", item))
        return result
    if value is None or value == "":
        return []
    normalized = value.value if isinstance(value, Enum) else value
    return [(path, canonical_json(normalized))]


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "N/A"
    return f"{numerator / denominator:.6f}"
