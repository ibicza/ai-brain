"""Atomic verified-candidate installation into RuleMemory."""

from __future__ import annotations

import json
from pathlib import Path

from ai_brain.rules.ast import parse_canonical_dsl
from ai_brain.rules.memory import RuleMemory, RuleRecord
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import property_verify
from ai_brain.stage1.approval import validate_approval
from ai_brain.stage1.models import (
    ApprovalEnvelope,
    InstalledRuleReceipt,
    RuleProposal,
    VerifiedCandidateBundle,
    VerifiedReviewArtifact,
    approval_hash,
    content_hash,
    proposal_hash,
    utc_now,
)
from ai_brain.stage1.version import RULE_MEMORY_SCHEMA_VERSION, STAGE1_VERSION


def install_candidate(
    *,
    memory_path: Path,
    proposal: RuleProposal,
    candidate: VerifiedCandidateBundle,
    review: VerifiedReviewArtifact,
    approval: ApprovalEnvelope,
) -> tuple[RuleRecord, InstalledRuleReceipt]:
    validate_approval(proposal, candidate, review, approval)
    if proposal.specification is None:
        raise ValueError("Proposal has no specification")
    program, _ = parse_canonical_dsl(candidate.candidate_dsl)
    verified = property_verify(program, proposal.specification, large=True)
    if not verified.accepted:
        raise ValueError("Candidate failed installation-time re-verification")
    memory = (
        RuleMemory.load_with_backup(memory_path)
        if memory_path.exists()
        else RuleMemory()
    )
    provenance = json.dumps(
        {
            "proposal_id": proposal.proposal_id,
            "proposal_hash": proposal_hash(proposal),
            "specification_hash": candidate.specification_hash,
            "source_kind": str(proposal.source_kind),
            "original_input_hash": content_hash(proposal.original_input),
            "approval_identity": approval.identity,
            "approval_identity_type": approval.identity_type,
            "approval_timestamp": approval.timestamp,
            "candidate_hash": candidate.candidate_hash,
            "evidence_hash": candidate.evidence_hash,
            "verified_review_hash": review.review_hash,
            "approval_hash": approval_hash(approval),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    record = memory.add(
        program,
        proposal.specification,
        VerificationStatus.PROPERTY_VERIFIED,
        provenance=provenance,
        verification_evidence=candidate.verification_evidence,
    )
    memory.save(memory_path)
    receipt = InstalledRuleReceipt(
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal_hash(proposal),
        installed_rule_id=record.rule_id,
        rule_semantic_hash=record.semantic_hash,
        specification_hash=candidate.specification_hash,
        candidate_hash=candidate.candidate_hash,
        evidence_hash=candidate.evidence_hash,
        verified_review_hash=review.review_hash,
        approval_hash=approval_hash(approval),
        rule_memory_schema_version=RULE_MEMORY_SCHEMA_VERSION,
        stage1_version=STAGE1_VERSION,
        installation_timestamp=utc_now(),
    )
    return record, receipt
