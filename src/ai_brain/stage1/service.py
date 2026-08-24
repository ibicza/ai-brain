"""Public Stage-1 production service API."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from ai_brain.rules.ast import REG_BINDING, parse_canonical_dsl
from ai_brain.rules.memory import RuleMemory, RuleRecord
from ai_brain.stage1.acquisition import verify_proposal
from ai_brain.stage1.approval import approve_candidate
from ai_brain.stage1.audit import AuditLog
from ai_brain.stage1.clarification import ClarificationRequest, clarification_for
from ai_brain.stage1.controlled_language import PARSER_NAME, parse_controlled_language
from ai_brain.stage1.execution import execute_rule
from ai_brain.stage1.installer import install_candidate
from ai_brain.stage1.models import (
    ApprovalDecision,
    ApprovalEnvelope,
    ExecutionResult,
    IssueCode,
    ProposalIssue,
    ProposalStatus,
    RuleProposal,
    SourceKind,
    VerifiedCandidateBundle,
    content_hash,
    specification_hash,
    utc_now,
)
from ai_brain.stage1.review import ReviewView, build_review_view
from ai_brain.stage1.specifications import (
    infer_family,
    specification_from_dict,
    validate_specification,
)
from ai_brain.stage1.version import (
    CONTROLLED_LANGUAGE_VERSION,
    SPECIFICATION_SCHEMA_VERSION,
)


class Stage1Service:
    def __init__(self, *, memory_path: Path, audit_path: Path) -> None:
        self.memory_path = memory_path
        self.audit = AuditLog(audit_path)

    def propose_language(
        self, text: str, *, language: str | None = None
    ) -> RuleProposal:
        received = self._received(SourceKind.CONTROLLED_LANGUAGE, text, language)
        parsed = received.transition(ProposalStatus.PARSED)
        outcome = parse_controlled_language(text, language)
        proposal = parsed.transition(
            outcome.status,
            language=outcome.language,
            specification=outcome.specification,
            semantic_family=outcome.family,
            issues=outcome.issues,
            parser_name=PARSER_NAME,
            parser_version=CONTROLLED_LANGUAGE_VERSION,
            specification_hash=(
                specification_hash(outcome.specification)
                if outcome.specification
                else None
            ),
            provenance=(
                {
                    "event": "parsed",
                    "partial_actions": [list(item) for item in outcome.partial_actions],
                },
            ),
        )
        self._audit_proposal("PROPOSAL_PARSED", proposal)
        return proposal

    def propose_form(self, row: dict[str, Any]) -> RuleProposal:
        original = json.dumps(row, ensure_ascii=False, sort_keys=True)
        received = self._received(SourceKind.FORM, original, None)
        parsed = received.transition(ProposalStatus.PARSED)
        try:
            specification = specification_from_dict(row)
            issues = validate_specification(specification)
            family = infer_family(specification)
            if issues or family is None:
                raise ValueError(",".join(issues) or "unsupported_family")
        except (TypeError, ValueError) as exc:
            proposal = parsed.transition(
                ProposalStatus.CONTRADICTORY,
                issues=(
                    ProposalIssue(IssueCode.INVALID_SCHEMA, "specification", str(exc)),
                ),
                parser_name="strict_form_v1",
                parser_version=str(SPECIFICATION_SCHEMA_VERSION),
            )
        else:
            proposal = parsed.transition(
                ProposalStatus.SUPPORTED_FOR_REVIEW,
                specification=specification,
                semantic_family=family,
                specification_hash=specification_hash(specification),
                parser_name="strict_form_v1",
                parser_version=str(SPECIFICATION_SCHEMA_VERSION),
            )
        self._audit_proposal("PROPOSAL_PARSED", proposal)
        return proposal

    def propose_dsl(self, dsl: str, specification_row: dict[str, Any]) -> RuleProposal:
        original = json.dumps(
            {"dsl": dsl, "specification": specification_row},
            ensure_ascii=False,
            sort_keys=True,
        )
        received = self._received(SourceKind.CANONICAL_DSL, original, None)
        parsed = received.transition(ProposalStatus.PARSED)
        try:
            _, binding = parse_canonical_dsl(dsl)
            if binding.mapping != REG_BINDING:
                raise ValueError(
                    "Canonical DSL must use the frozen A-D to R0-R3 binding"
                )
            specification = specification_from_dict(specification_row)
            problems = validate_specification(specification)
            if problems:
                raise ValueError(",".join(problems))
        except (TypeError, ValueError) as exc:
            proposal = parsed.transition(
                ProposalStatus.CONTRADICTORY,
                issues=(ProposalIssue(IssueCode.INVALID_SCHEMA, "dsl", str(exc)),),
                parser_name="canonical_dsl_v1",
                parser_version="1",
            )
        else:
            proposal = parsed.transition(
                ProposalStatus.SUPPORTED_FOR_REVIEW,
                specification=specification,
                semantic_family=infer_family(specification),
                specification_hash=specification_hash(specification),
                parser_name="canonical_dsl_v1",
                parser_version="1",
                provenance=({"event": "canonical_candidate", "dsl": dsl},),
            )
        self._audit_proposal("PROPOSAL_PARSED", proposal)
        return proposal

    def clarify(self, proposal: RuleProposal, answer: str) -> RuleProposal:
        if proposal.status != ProposalStatus.CLARIFICATION_REQUIRED:
            raise ValueError("Proposal is not awaiting clarification")
        if any(row.get("event") == "clarification" for row in proposal.provenance):
            raise ValueError("The one-round clarification budget is exhausted")
        outcome = parse_controlled_language(
            f"{proposal.original_input}; {answer}", proposal.language
        )
        status = (
            ProposalStatus.EDITED
            if outcome.status == ProposalStatus.SUPPORTED_FOR_REVIEW
            else outcome.status
        )
        updated = proposal.transition(
            status,
            specification=outcome.specification,
            semantic_family=outcome.family,
            issues=outcome.issues,
            specification_hash=(
                specification_hash(outcome.specification)
                if outcome.specification
                else None
            ),
            provenance=(
                *proposal.provenance,
                {"event": "clarification", "answer": answer},
            ),
            revision=proposal.revision + 1,
        )
        self._audit_proposal("CLARIFICATION_RESOLVED", updated)
        return updated

    def edit(self, proposal: RuleProposal, row: dict[str, Any]) -> RuleProposal:
        if proposal.status not in {
            ProposalStatus.SUPPORTED_FOR_REVIEW,
            ProposalStatus.REVIEWED,
            ProposalStatus.VERIFIED,
        }:
            raise ValueError("Proposal cannot be edited in its current state")
        specification = specification_from_dict(row)
        problems = validate_specification(specification)
        if problems:
            raise ValueError(f"Edited specification invalid: {', '.join(problems)}")
        updated = proposal.transition(
            ProposalStatus.EDITED,
            specification=specification,
            semantic_family=infer_family(specification),
            specification_hash=specification_hash(specification),
            issues=(),
            provenance=(*proposal.provenance, {"event": "edited"}),
            revision=proposal.revision + 1,
        )
        self._audit_proposal("PROPOSAL_EDITED_VERIFICATION_INVALIDATED", updated)
        return updated

    def review(self, proposal: RuleProposal) -> tuple[RuleProposal, ReviewView]:
        if proposal.status not in {
            ProposalStatus.SUPPORTED_FOR_REVIEW,
            ProposalStatus.EDITED,
        }:
            raise ValueError("Only a supported or edited proposal can be reviewed")
        reviewed = proposal.transition(ProposalStatus.REVIEWED)
        self._audit_proposal("PROPOSAL_REVIEWED", reviewed)
        return reviewed, build_review_view(reviewed)

    def verify(
        self, proposal: RuleProposal
    ) -> tuple[RuleProposal, VerifiedCandidateBundle]:
        if proposal.status != ProposalStatus.REVIEWED:
            raise ValueError("Review is required before verification")
        verified = proposal.transition(ProposalStatus.VERIFIED)
        canonical = next(
            (
                str(row["dsl"])
                for row in proposal.provenance
                if row.get("event") == "canonical_candidate"
            ),
            None,
        )
        candidate = verify_proposal(verified, canonical_candidate=canonical)
        self.audit.append(
            "CANDIDATE_VERIFIED",
            {
                "candidate_hash": candidate.candidate_hash,
                "evidence_hash": candidate.evidence_hash,
            },
            proposal.proposal_id,
        )
        return verified, candidate

    def approve(
        self,
        proposal: RuleProposal,
        candidate: VerifiedCandidateBundle,
        *,
        identity: str,
        identity_type: str = "USER",
        decision: ApprovalDecision = ApprovalDecision.APPROVE,
    ) -> tuple[RuleProposal, ApprovalEnvelope]:
        if proposal.status != ProposalStatus.VERIFIED:
            raise ValueError("Only a verified proposal can be approved")
        approval = approve_candidate(
            proposal,
            candidate,
            identity=identity,
            identity_type=identity_type,
            decision=decision,
        )
        if decision != ApprovalDecision.APPROVE:
            self.audit.append(
                "APPROVAL_REJECTED", asdict(approval), proposal.proposal_id
            )
            return proposal, approval
        approved = proposal.transition(ProposalStatus.APPROVED)
        self.audit.append("PROPOSAL_APPROVED", asdict(approval), proposal.proposal_id)
        return approved, approval

    def install(
        self,
        proposal: RuleProposal,
        candidate: VerifiedCandidateBundle,
        approval: ApprovalEnvelope,
    ) -> tuple[RuleProposal, RuleRecord]:
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError("Approval is required before installation")
        record = install_candidate(
            memory_path=self.memory_path,
            proposal=proposal,
            candidate=candidate,
            approval=approval,
        )
        installed = proposal.transition(ProposalStatus.INSTALLED)
        self.audit.append(
            "RULE_INSTALLED", {"rule_id": record.rule_id}, proposal.proposal_id
        )
        return installed, record

    def execute(
        self, proposal: RuleProposal, rule_id: str, state: dict[str, int]
    ) -> tuple[RuleProposal, ExecutionResult]:
        if proposal.status not in {ProposalStatus.INSTALLED, ProposalStatus.EXECUTED}:
            raise ValueError("An installed rule is required for execution")
        result = execute_rule(self.memory_path, rule_id, state)
        executed = proposal.transition(ProposalStatus.EXECUTED)
        result = replace(result, proposal_id=proposal.proposal_id)
        self.audit.append("RULE_EXECUTED", asdict(result), proposal.proposal_id)
        return executed, result

    def list_rules(self, *, active_only: bool = False) -> list[RuleRecord]:
        if not self.memory_path.exists():
            return []
        memory = RuleMemory.load_with_backup(self.memory_path)
        return memory.active_records() if active_only else list(memory.records.values())

    def inspect_rule(self, rule_id: str) -> RuleRecord:
        memory = RuleMemory.load_with_backup(self.memory_path)
        return memory.records[rule_id]

    def clarification(self, proposal: RuleProposal) -> ClarificationRequest | None:
        return clarification_for(proposal)

    def _received(
        self, source_kind: SourceKind, original: str, language: str | None
    ) -> RuleProposal:
        identifier = f"proposal-{content_hash({'source_kind': source_kind, 'input': original})[:16]}"
        proposal = RuleProposal(
            identifier,
            source_kind,
            original,
            language,
            ProposalStatus.RECEIVED,
            created_at=utc_now(),
        )
        self._audit_proposal("PROPOSAL_RECEIVED", proposal)
        return proposal

    def _audit_proposal(self, event: str, proposal: RuleProposal) -> None:
        self.audit.append(
            event,
            {"status": str(proposal.status), "revision": proposal.revision},
            proposal.proposal_id,
        )
