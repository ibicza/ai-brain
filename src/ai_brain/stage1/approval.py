"""Hash-bound explicit approval creation and validation."""

from __future__ import annotations

from ai_brain.stage1.models import (
    ApprovalDecision,
    ApprovalEnvelope,
    RuleProposal,
    VerifiedCandidateBundle,
    content_hash,
    proposal_hash,
    specification_hash,
    utc_now,
)
from ai_brain.stage1.version import STAGE1_VERSION


def approve_candidate(
    proposal: RuleProposal,
    candidate: VerifiedCandidateBundle,
    *,
    identity: str,
    identity_type: str = "USER",
    decision: ApprovalDecision = ApprovalDecision.APPROVE,
) -> ApprovalEnvelope:
    validate_candidate_binding(proposal, candidate)
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


def validate_approval(
    proposal: RuleProposal,
    candidate: VerifiedCandidateBundle,
    approval: ApprovalEnvelope,
) -> None:
    validate_candidate_binding(proposal, candidate)
    if approval.stage1_version != STAGE1_VERSION:
        raise ValueError("Stale approval: stage1_version mismatch")
    if approval.decision != ApprovalDecision.APPROVE:
        raise ValueError("Explicit APPROVE decision is required")
    for field in (
        "proposal_id",
        "proposal_hash",
        "specification_hash",
        "candidate_hash",
        "evidence_hash",
    ):
        expected = (
            getattr(proposal, field)
            if field == "proposal_id"
            else proposal_hash(proposal)
            if field == "proposal_hash"
            else getattr(candidate, field)
        )
        if getattr(approval, field) != expected:
            raise ValueError(f"Stale approval: {field} mismatch")
