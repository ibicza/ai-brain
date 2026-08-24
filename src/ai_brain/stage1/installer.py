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
    RuleProposal,
    VerifiedCandidateBundle,
)


def install_candidate(
    *,
    memory_path: Path,
    proposal: RuleProposal,
    candidate: VerifiedCandidateBundle,
    approval: ApprovalEnvelope,
) -> RuleRecord:
    validate_approval(proposal, candidate, approval)
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
            "source_kind": str(proposal.source_kind),
            "original_input": proposal.original_input,
            "approval_identity": approval.identity,
            "approval_identity_type": approval.identity_type,
            "approval_timestamp": approval.timestamp,
            "candidate_hash": candidate.candidate_hash,
            "evidence_hash": candidate.evidence_hash,
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
    return record
