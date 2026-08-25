"""Hash-bound explicit approval creation and validation."""

from __future__ import annotations

from ai_brain.stage1.models import (
    ApprovalDecision,
    ApprovalEnvelope,
    RuleProposal,
    VerifiedCandidateBundle,
    VerifiedReviewArtifact,
    content_hash,
    proposal_hash,
    specification_hash,
    utc_now,
    verified_review_content_hash,
)
from ai_brain.stage1.version import STAGE1_VERSION


def approve_candidate(
    proposal: RuleProposal,
    candidate: VerifiedCandidateBundle,
    review: VerifiedReviewArtifact,
    *,
    identity: str,
    identity_type: str = "USER",
    decision: ApprovalDecision = ApprovalDecision.APPROVE,
) -> ApprovalEnvelope:
    validate_verified_review(proposal, candidate, review)
    return ApprovalEnvelope(
        decision=decision,
        identity=identity,
        identity_type=identity_type,
        timestamp=utc_now(),
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal_hash(proposal),
        specification_hash=candidate.specification_hash,
        candidate_hash=candidate.candidate_hash,
        evidence_hash=candidate.evidence_hash,
        verified_review_hash=review.review_hash,
    )


def validate_candidate_binding(
    proposal: RuleProposal, candidate: VerifiedCandidateBundle
) -> None:
    if proposal.specification is None:
        raise ValueError("Proposal has no specification")
    expected = {
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal_hash(proposal),
        "specification_hash": specification_hash(proposal.specification),
    }
    for field, value in expected.items():
        if getattr(candidate, field) != value:
            raise ValueError(f"Stale candidate: {field} mismatch")
    if content_hash(candidate.candidate_dsl) != candidate.candidate_hash:
        raise ValueError("Stale candidate: candidate_hash mismatch")
    if content_hash(candidate.verification_evidence) != candidate.evidence_hash:
        raise ValueError("Stale candidate: evidence_hash mismatch")


def validate_verified_review(
    proposal: RuleProposal,
    candidate: VerifiedCandidateBundle,
    review: VerifiedReviewArtifact,
) -> None:
    validate_candidate_binding(proposal, candidate)
    if review.stage1_version != STAGE1_VERSION:
        raise ValueError("Stale verified review: stage1_version mismatch")
    if verified_review_content_hash(review) != review.review_hash:
        raise ValueError("Stale verified review: review_hash mismatch")
    expected = {
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal_hash(proposal),
        "specification_hash": candidate.specification_hash,
        "candidate_hash": candidate.candidate_hash,
        "evidence_hash": candidate.evidence_hash,
    }
    for field, value in expected.items():
        if getattr(review, field) != value:
            raise ValueError(f"Stale verified review: {field} mismatch")
    if review.candidate_dsl != candidate.candidate_dsl:
        raise ValueError("Stale verified review: candidate_dsl mismatch")
    verification_rows = {
        "static_verification_result": "static_verification",
        "abstract_verification_result": "abstract_verification",
        "property_verification_result": "property_verification",
    }
    for review_field, evidence_field in verification_rows.items():
        if getattr(review, review_field) != candidate.verification_evidence.get(
            evidence_field
        ):
            raise ValueError(f"Stale verified review: {review_field} mismatch")
    if review.verification_evidence != candidate.verification_evidence:
        raise ValueError("Stale verified review: verification_evidence mismatch")


def validate_approval(
    proposal: RuleProposal,
    candidate: VerifiedCandidateBundle,
    review: VerifiedReviewArtifact,
    approval: ApprovalEnvelope,
) -> None:
    validate_verified_review(proposal, candidate, review)
    if approval.stage1_version != STAGE1_VERSION:
        raise ValueError("Stale approval: stage1_version mismatch")
    if approval.decision != ApprovalDecision.APPROVE:
        raise ValueError("Explicit APPROVE decision is required")
    expected = {
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal_hash(proposal),
        "specification_hash": candidate.specification_hash,
        "candidate_hash": candidate.candidate_hash,
        "evidence_hash": candidate.evidence_hash,
        "verified_review_hash": review.review_hash,
    }
    for field, value in expected.items():
        if getattr(approval, field) != value:
            raise ValueError(f"Stale approval: {field} mismatch")
