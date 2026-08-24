"""Explicit trusted approval gate for language-derived rules."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import StrEnum

from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    canonical_specification_json,
    validate_proposal,
)
from ai_brain.rules.ast import parse_canonical_dsl
from ai_brain.rules.blackbox import PublicAcquisitionResult
from ai_brain.rules.memory import RuleMemory, RuleRecord
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT_SPECIFICATION = "EDIT_SPECIFICATION"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"


@dataclass(frozen=True)
class Approval:
    decision: ApprovalDecision
    identity: str
    identity_type: str
    specification_signature: str

    def __post_init__(self) -> None:
        if not self.identity.strip():
            raise ValueError("approval identity is required")
        if self.identity_type not in {"USER", "TRUSTED_SUPERVISOR"}:
            raise ValueError("identity_type must be USER or TRUSTED_SUPERVISOR")


@dataclass(frozen=True)
class ApprovalView:
    original_language: str
    parsed_specification: str
    warnings: tuple[str, ...]
    verification_status: str
    generated_rule_summary: str


def approval_view(
    proposal: LanguageProposal, result: PublicAcquisitionResult
) -> ApprovalView:
    specification = (
        canonical_specification_json(proposal.specification)
        if proposal.specification is not None
        else "null"
    )
    return ApprovalView(
        proposal.original_text,
        specification,
        tuple(issue.code for issue in validate_proposal(proposal)),
        result.status,
        result.candidate_ast or "",
    )


def edit_proposal(
    proposal: LanguageProposal, edited: ProgramSpecification
) -> LanguageProposal:
    return replace(
        proposal,
        status=ParseStatus.SUPPORTED,
        specification=edited,
        issues=(),
        confidence=1.0,
        provenance=(
            *proposal.provenance,
            ("model_proposal", canonical_specification_json(proposal.specification))
            if proposal.specification is not None
            else ("model_proposal", "null"),
            ("user_edit", canonical_specification_json(edited)),
            ("requires_reverification", "true"),
        ),
    )


def store_approved_language_rule(
    *,
    memory: RuleMemory,
    proposal: LanguageProposal,
    acquisition: PublicAcquisitionResult,
    approval: Approval,
) -> RuleRecord:
    issues = validate_proposal(proposal)
    if proposal.status != ParseStatus.SUPPORTED or proposal.specification is None:
        raise ValueError("Only a supported complete proposal can be installed")
    if issues:
        raise ValueError(f"Specification validation failed: {issues[0].code}")
    signature = canonical_specification_json(proposal.specification)
    if approval.decision != ApprovalDecision.APPROVE:
        raise ValueError("Explicit APPROVE is required")
    if approval.specification_signature != signature:
        raise ValueError("Approval does not match the final specification")
    if acquisition.status != VerificationStatus.PROPERTY_VERIFIED:
        raise ValueError("PROPERTY_VERIFIED acquisition is required")
    if not acquisition.candidate_ast or not acquisition.verification_evidence:
        raise ValueError("Verified candidate and evidence are required")
    evidence = dict(acquisition.verification_evidence)
    if not evidence.get("accepted") or evidence.get("status") != str(
        VerificationStatus.PROPERTY_VERIFIED
    ):
        raise ValueError("Acquisition evidence is not property verified")
    program, _ = parse_canonical_dsl(acquisition.candidate_ast)
    provenance = json.dumps(
        {
            "source": "M-23 language frontend",
            "original_language": proposal.original_text,
            "model_proposal": signature,
            "edits": list(proposal.provenance),
            "approval_identity": approval.identity,
            "approval_identity_type": approval.identity_type,
            "verification_evidence": evidence,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return memory.add(
        program,
        proposal.specification,
        VerificationStatus.PROPERTY_VERIFIED,
        provenance=provenance,
        verification_evidence=evidence,
    )
