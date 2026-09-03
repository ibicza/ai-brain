from __future__ import annotations

from dataclasses import asdict, replace

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash, normalize_datetime, utc_now
from ai_brain.stage3.acquisition.java_pipeline import (
    VerifiedJavaTrustAuthorization,
    assert_java_proposal_state_authority,
)
from ai_brain.stage3.acquisition.java_production import (
    VerifiedJavaProductionAuthorization,
    assert_java_production_authority,
)
from ai_brain.stage3.acquisition.models import (
    AcquisitionReview,
    ExtractionMethod,
    KnowledgeProposal,
    ProposalApproval,
    ProposalStatus,
    ReviewDecision,
)
from ai_brain.stage3.acquisition.proposals import with_status
from ai_brain.stage3.acquisition.version import ACQUISITION_REVIEW_SCHEMA_VERSION
from ai_brain.stage3.knowledge_ir.records import KnowledgeContent


def review_proposal(
    proposal: KnowledgeProposal,
    *,
    reviewer_identity: str,
    reviewer_type: ActorIdentityType,
    decision: ReviewDecision,
    rationale: str,
    edited_content: KnowledgeContent | None = None,
    timestamp: str | None = None,
    trust_authorization: (
        VerifiedJavaTrustAuthorization | VerifiedJavaProductionAuthorization | None
    ) = None,
    external_user_approval_hash: str | None = None,
) -> tuple[KnowledgeProposal, AcquisitionReview, ProposalApproval | None]:
    approving = decision in {ReviewDecision.APPROVE, ReviewDecision.EDIT_AND_APPROVE}
    if proposal.extraction_method is ExtractionMethod.JAVA_AST:
        if proposal.status is ProposalStatus.VERIFIED:
            raise ValueError(
                "Java VERIFIED status contradicts semantic trust authority"
            )
        if approving:
            if trust_authorization is None:
                raise ValueError("Java approval requires authoritative trust closure")
            if isinstance(trust_authorization, VerifiedJavaProductionAuthorization):
                assert_java_production_authority(proposal, trust_authorization)
                if (
                    reviewer_type is ActorIdentityType.USER
                    and not external_user_approval_hash
                ):
                    raise ValueError(
                        "USER approval requires an external approval artifact"
                    )
            else:
                assert_java_proposal_state_authority(proposal, trust_authorization)
            if edited_content is not None:
                raise ValueError("edited Java content requires a new trust evaluation")
    if approving and (
        reviewer_type is ActorIdentityType.MODEL or not reviewer_identity.strip()
    ):
        raise ValueError("MODEL or blank reviewer cannot approve acquisition")
    if decision is ReviewDecision.EDIT_AND_APPROVE and edited_content is None:
        raise ValueError("edited approval requires hash-bound content")
    if decision is not ReviewDecision.EDIT_AND_APPROVE and edited_content is not None:
        raise ValueError("content edit requires EDIT_AND_APPROVE")
    stamp = timestamp or utc_now()
    normalize_datetime(stamp)
    updated = (
        replace(proposal, proposed_content=edited_content)
        if edited_content is not None
        else proposal
    )
    status = {
        ReviewDecision.APPROVE: ProposalStatus.APPROVED,
        ReviewDecision.EDIT_AND_APPROVE: ProposalStatus.APPROVED,
        ReviewDecision.REJECT: ProposalStatus.REJECTED,
        ReviewDecision.REVIEW_REQUIRED: ProposalStatus.REVIEW_REQUIRED,
        ReviewDecision.NEEDS_NEW_CAPABILITY: ProposalStatus.NEEDS_NEW_CAPABILITY,
    }[decision]
    updated = with_status(updated, status)
    review_body = {
        "review_id": "",
        "proposal_hash": proposal.proposal_hash,
        "reviewer_identity": reviewer_identity,
        "reviewer_type": reviewer_type,
        "decision": decision,
        "edited_content_hash": content_hash(asdict(edited_content))
        if edited_content is not None
        else None,
        "rationale": rationale,
        "timestamp": stamp,
        "schema_version": ACQUISITION_REVIEW_SCHEMA_VERSION,
    }
    review_body["review_id"] = f"review.{content_hash(review_body)[:32]}"
    review = AcquisitionReview(**review_body, review_hash=content_hash(review_body))
    approval = None
    if approving:
        body = {
            "proposal_id": proposal.proposal_id,
            "original_proposal_hash": proposal.proposal_hash,
            "approved_proposal_hash": updated.proposal_hash,
            "review_hash": review.review_hash,
        }
        approval = ProposalApproval(**body, approval_hash=content_hash(body))
    return updated, review, approval
