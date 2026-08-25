"""Public Stage-1 production service API."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.rules.ast import REG_BINDING, parse_canonical_dsl
from ai_brain.rules.memory import (
    RuleMemory,
    RuleMemoryIntegrityError,
    RuleMemoryIOError,
    RuleMemoryRecoveryError,
    RuleMemoryRecoveryRequiredError,
    RuleRecord,
    StoredRuleParseError,
    recover_rule_memory,
)
from ai_brain.stage1.acquisition import verify_proposal
from ai_brain.stage1.approval import approve_candidate
from ai_brain.stage1.audit import AuditLog
from ai_brain.stage1.clarification import ClarificationRequest, clarification_for
from ai_brain.stage1.controlled_language import PARSER_NAME, parse_controlled_language
from ai_brain.stage1.execution import BoundedExecutionError, execute_rule
from ai_brain.stage1.installer import install_candidate
from ai_brain.stage1.models import (
    ApprovalDecision,
    ApprovalEnvelope,
    ExecutionFailureCode,
    ExecutionLimits,
    ExecutionResult,
    InstalledRuleReceipt,
    IssueCode,
    ProposalIssue,
    ProposalStatus,
    RuleProposal,
    SourceKind,
    VerifiedCandidateBundle,
    VerifiedReviewArtifact,
    approval_hash,
    content_hash,
    proposal_hash,
    specification_hash,
    utc_now,
)
from ai_brain.stage1.review import (
    ReviewView,
    build_review_view,
    build_verified_review,
)
from ai_brain.stage1.specifications import (
    infer_family,
    specification_from_dict,
    validate_specification,
)
from ai_brain.stage1.version import (
    CONTROLLED_LANGUAGE_VERSION,
    RULE_MEMORY_SCHEMA_VERSION,
    SPECIFICATION_SCHEMA_VERSION,
    STAGE1_VERSION,
)


class Stage1Service:
    def __init__(
        self,
        *,
        memory_path: Path,
        audit_path: Path,
        proposal_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.memory_path = memory_path
        self.audit = AuditLog(audit_path)
        self._proposal_id_factory = proposal_id_factory or _default_proposal_id
        self._issued_proposal_ids: set[str] = set()

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
        self._audit_parsed(proposal)
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
        self._audit_parsed(proposal)
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
        self._audit_parsed(proposal)
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
                {"event": "clarification", "answer_hash": content_hash(answer)},
            ),
            revision=proposal.revision + 1,
        )
        self._audit_parsed(updated, event="CLARIFICATION_RESOLVED")
        return updated

    def edit(self, proposal: RuleProposal, row: dict[str, Any]) -> RuleProposal:
        if proposal.status not in {
            ProposalStatus.SUPPORTED_FOR_REVIEW,
            ProposalStatus.REVIEWED,
            ProposalStatus.VERIFIED,
            ProposalStatus.VERIFIED_REVIEWED,
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
        self._audit_parsed(updated, event="PROPOSAL_EDITED_VERIFICATION_INVALIDATED")
        return updated

    def review(self, proposal: RuleProposal) -> tuple[RuleProposal, ReviewView]:
        if proposal.status not in {
            ProposalStatus.SUPPORTED_FOR_REVIEW,
            ProposalStatus.EDITED,
        }:
            raise ValueError("Only a supported or edited proposal can be reviewed")
        reviewed = proposal.transition(ProposalStatus.REVIEWED)
        view = build_review_view(reviewed)
        self.audit.append(
            "PROPOSAL_REVIEWED",
            {
                "proposal_hash": proposal_hash(reviewed),
                "specification_hash": reviewed.specification_hash,
                "review_hash": content_hash(view),
                "revision": reviewed.revision,
                "stage1_version": STAGE1_VERSION,
            },
            reviewed.proposal_id,
        )
        return reviewed, view

    def verify(
        self, proposal: RuleProposal
    ) -> tuple[RuleProposal, VerifiedCandidateBundle]:
        if proposal.status != ProposalStatus.REVIEWED:
            raise ValueError("Review is required before verification")
        verified = proposal.transition(ProposalStatus.VERIFIED)
        canonical = next(
            (
                row["dsl"]
                for row in proposal.provenance
                if row.get("event") == "canonical_candidate"
            ),
            None,
        )
        if canonical is not None and not isinstance(canonical, str):
            raise TypeError("Canonical candidate provenance must be a string")
        try:
            candidate = verify_proposal(verified, canonical_candidate=canonical)
        except ValueError as exc:
            self.audit.append(
                "VERIFICATION_FAILED",
                {
                    "proposal_hash": proposal_hash(verified),
                    "specification_hash": verified.specification_hash,
                    "failure_type": type(exc).__name__,
                    "failure_message_hash": content_hash(str(exc)),
                    "revision": verified.revision,
                    "stage1_version": STAGE1_VERSION,
                },
                verified.proposal_id,
            )
            raise
        self.audit.append(
            "CANDIDATE_VERIFIED",
            {
                "proposal_hash": candidate.proposal_hash,
                "specification_hash": candidate.specification_hash,
                "candidate_hash": candidate.candidate_hash,
                "evidence_hash": candidate.evidence_hash,
                "compiler_name": candidate.compiler_name,
                "revision": verified.revision,
                "stage1_version": STAGE1_VERSION,
            },
            verified.proposal_id,
        )
        return verified, candidate

    def review_verification(
        self, proposal: RuleProposal, candidate: VerifiedCandidateBundle
    ) -> tuple[RuleProposal, VerifiedReviewArtifact]:
        if proposal.status != ProposalStatus.VERIFIED:
            raise ValueError("Only a verified proposal can review verification")
        review = build_verified_review(proposal, candidate)
        reviewed = proposal.transition(ProposalStatus.VERIFIED_REVIEWED)
        self.audit.append(
            "VERIFIED_REVIEWED",
            {
                "proposal_hash": review.proposal_hash,
                "specification_hash": review.specification_hash,
                "verified_review_hash": review.review_hash,
                "candidate_hash": review.candidate_hash,
                "evidence_hash": review.evidence_hash,
                "revision": reviewed.revision,
                "stage1_version": STAGE1_VERSION,
            },
            reviewed.proposal_id,
        )
        return reviewed, review

    def approve(
        self,
        proposal: RuleProposal,
        candidate: VerifiedCandidateBundle,
        review: VerifiedReviewArtifact,
        *,
        identity: str,
        identity_type: str = "USER",
        decision: ApprovalDecision = ApprovalDecision.APPROVE,
    ) -> tuple[RuleProposal, ApprovalEnvelope]:
        if proposal.status != ProposalStatus.VERIFIED_REVIEWED:
            raise ValueError("Verified candidate review is required before approval")
        approval = approve_candidate(
            proposal,
            candidate,
            review,
            identity=identity,
            identity_type=identity_type,
            decision=decision,
        )
        if decision != ApprovalDecision.APPROVE:
            self.audit.append(
                "APPROVAL_REJECTED",
                {
                    "approval_hash": approval_hash(approval),
                    "identity_type": approval.identity_type,
                    "revision": proposal.revision,
                },
                proposal.proposal_id,
            )
            return proposal, approval
        approved = proposal.transition(ProposalStatus.APPROVED)
        self.audit.append(
            "PROPOSAL_APPROVED",
            {
                "approval_hash": approval_hash(approval),
                "identity_type": approval.identity_type,
                "proposal_hash": approval.proposal_hash,
                "specification_hash": approval.specification_hash,
                "candidate_hash": approval.candidate_hash,
                "evidence_hash": approval.evidence_hash,
                "verified_review_hash": approval.verified_review_hash,
                "revision": approved.revision,
                "stage1_version": approval.stage1_version,
            },
            approved.proposal_id,
        )
        return approved, approval

    def install(
        self,
        proposal: RuleProposal,
        candidate: VerifiedCandidateBundle,
        review: VerifiedReviewArtifact,
        approval: ApprovalEnvelope,
    ) -> tuple[RuleProposal, RuleRecord, InstalledRuleReceipt]:
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError("Approval is required before installation")
        try:
            record, receipt = install_candidate(
                memory_path=self.memory_path,
                proposal=proposal,
                candidate=candidate,
                review=review,
                approval=approval,
            )
        except (
            RuleMemoryIntegrityError,
            RuleMemoryRecoveryError,
            RuleMemoryRecoveryRequiredError,
            RuleMemoryIOError,
        ) as exc:
            self.audit.append(
                "RULE_MEMORY_WRITE_FAILED",
                {
                    "failure_code": str(_memory_failure_code(exc)),
                    "proposal_hash": proposal_hash(proposal),
                    "specification_hash": proposal.specification_hash,
                    "revision": proposal.revision,
                    "stage1_version": STAGE1_VERSION,
                },
                proposal.proposal_id,
            )
            raise
        installed = proposal.transition(ProposalStatus.INSTALLED)
        self.audit.append(
            "RULE_INSTALLED",
            {
                "rule_id": record.rule_id,
                "rule_semantic_hash": record.semantic_hash,
                "memory_schema_version": RULE_MEMORY_SCHEMA_VERSION,
                "proposal_hash": receipt.proposal_hash,
                "specification_hash": receipt.specification_hash,
                "candidate_hash": receipt.candidate_hash,
                "evidence_hash": receipt.evidence_hash,
                "verified_review_hash": receipt.verified_review_hash,
                "approval_hash": receipt.approval_hash,
                "revision": installed.revision,
                "stage1_version": STAGE1_VERSION,
            },
            installed.proposal_id,
        )
        return installed, record, receipt

    def execute(
        self,
        proposal: RuleProposal,
        receipt: InstalledRuleReceipt,
        rule_id: str,
        state: dict[str, int],
        *,
        limits: ExecutionLimits | None = None,
    ) -> tuple[RuleProposal, ExecutionResult]:
        actual_limits = limits or ExecutionLimits()
        try:
            self._validate_receipt_binding(proposal, receipt, rule_id)
            result = execute_rule(
                self.memory_path,
                rule_id,
                state,
                proposal_id=proposal.proposal_id,
                limits=actual_limits,
            )
        except BoundedExecutionError as exc:
            self.audit.append(
                "EXECUTION_FAILED",
                {
                    "rule_id": rule_id,
                    "initial_state_hash": content_hash(state),
                    "failure_code": str(exc.code),
                    "executed_steps": exc.executed_steps,
                    "limits": asdict(actual_limits),
                    "revision": proposal.revision,
                    "stage1_version": STAGE1_VERSION,
                },
                proposal.proposal_id,
            )
            raise
        except (
            RuleMemoryIntegrityError,
            RuleMemoryRecoveryError,
            RuleMemoryRecoveryRequiredError,
            RuleMemoryIOError,
        ) as exc:
            self.audit.append(
                "EXECUTION_FAILED",
                {
                    "rule_id": rule_id,
                    "initial_state_hash": content_hash(state),
                    "failure_code": str(_memory_failure_code(exc)),
                    "executed_steps": 0,
                    "limits": asdict(actual_limits),
                    "revision": proposal.revision,
                    "stage1_version": STAGE1_VERSION,
                },
                proposal.proposal_id,
            )
            raise
        executed = proposal.transition(ProposalStatus.EXECUTED)
        self.audit.append(
            "RULE_EXECUTED",
            {
                "rule_id": rule_id,
                "initial_state_hash": content_hash(result.initial_state),
                "final_state_hash": content_hash(result.final_state),
                "execution_hash": result.execution_hash,
                "executed_steps": result.executed_steps,
                "trace_requested": result.trace_requested,
                "trace_truncated": result.trace_truncated,
                "revision": executed.revision,
                "stage1_version": STAGE1_VERSION,
            },
            proposal.proposal_id,
        )
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

    def recover_rule_memory(self) -> dict[str, Any]:
        try:
            _, evidence = recover_rule_memory(self.memory_path)
        except (
            RuleMemoryIntegrityError,
            RuleMemoryRecoveryError,
            RuleMemoryRecoveryRequiredError,
            RuleMemoryIOError,
        ) as exc:
            self.audit.append(
                "RULE_MEMORY_RECOVERY_FAILED",
                {
                    "failure_code": str(_memory_failure_code(exc)),
                    "memory_path_hash": content_hash(str(self.memory_path.resolve())),
                    "stage1_version": STAGE1_VERSION,
                },
            )
            raise
        self.audit.append(
            "RULE_MEMORY_RECOVERED",
            {
                **evidence,
                "evidence_hash": content_hash(evidence),
                "stage1_version": STAGE1_VERSION,
            },
        )
        return evidence

    def _received(
        self, source_kind: SourceKind, original: str, language: str | None
    ) -> RuleProposal:
        identifier = self._proposal_id_factory()
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("proposal_id_factory must return a non-empty string")
        existing_ids = {
            event.proposal_id
            for event in self.audit.replay()
            if event.proposal_id is not None
        }
        if identifier in self._issued_proposal_ids or identifier in existing_ids:
            raise ValueError("proposal_id_factory returned a duplicate proposal ID")
        self._issued_proposal_ids.add(identifier)
        proposal = RuleProposal(
            identifier,
            source_kind,
            original,
            language,
            ProposalStatus.RECEIVED,
            created_at=utc_now(),
        )
        self.audit.append(
            "PROPOSAL_RECEIVED",
            {
                "source_kind": str(source_kind),
                "original_input_hash": content_hash(original),
                "proposal_id": proposal.proposal_id,
                "revision": proposal.revision,
                "stage1_version": STAGE1_VERSION,
            },
            proposal.proposal_id,
        )
        return proposal

    def _audit_parsed(
        self, proposal: RuleProposal, *, event: str = "PROPOSAL_PARSED"
    ) -> None:
        self.audit.append(
            event,
            {
                "proposal_hash": proposal_hash(proposal),
                "specification_hash": proposal.specification_hash,
                "parser_name": proposal.parser_name,
                "parser_version": proposal.parser_version,
                "status": str(proposal.status),
                "revision": proposal.revision,
                "stage1_version": STAGE1_VERSION,
            },
            proposal.proposal_id,
        )

    def _validate_receipt_binding(
        self,
        proposal: RuleProposal,
        receipt: InstalledRuleReceipt,
        requested_rule_id: str,
    ) -> None:
        if proposal.status not in {ProposalStatus.INSTALLED, ProposalStatus.EXECUTED}:
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "An installed proposal is required for execution",
            )
        if receipt.stage1_version != STAGE1_VERSION:
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Receipt Stage-1 version mismatch",
            )
        if receipt.proposal_revision != proposal.revision:
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Receipt proposal revision mismatch",
            )
        if receipt.rule_memory_schema_version != RULE_MEMORY_SCHEMA_VERSION:
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Receipt RuleMemory schema version mismatch",
            )
        if (
            receipt.proposal_id != proposal.proposal_id
            or receipt.proposal_hash != proposal_hash(proposal)
        ):
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Receipt does not belong to proposal",
            )
        if requested_rule_id != receipt.installed_rule_id:
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Requested rule does not match installed receipt",
            )
        memory = RuleMemory.load_with_backup(self.memory_path)
        record = memory.records.get(requested_rule_id)
        if (
            record is None
            or record.semantic_hash != receipt.rule_semantic_hash
            or specification_hash(record.specification) != receipt.specification_hash
        ):
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Receipt does not match RuleMemory record",
            )
        try:
            provenance = json.loads(record.provenance)
        except (TypeError, json.JSONDecodeError) as exc:
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Installed rule provenance is malformed",
            ) from exc
        expected = {
            "proposal_id": receipt.proposal_id,
            "proposal_revision": receipt.proposal_revision,
            "proposal_hash": receipt.proposal_hash,
            "specification_hash": receipt.specification_hash,
            "candidate_hash": receipt.candidate_hash,
            "evidence_hash": receipt.evidence_hash,
            "verified_review_hash": receipt.verified_review_hash,
            "approval_hash": receipt.approval_hash,
        }
        if not isinstance(provenance, dict) or any(
            provenance.get(name) != value for name, value in expected.items()
        ):
            raise BoundedExecutionError(
                ExecutionFailureCode.RULE_BINDING_MISMATCH,
                "Receipt does not match installed rule provenance",
            )


def _default_proposal_id() -> str:
    return f"proposal-{uuid.uuid4().hex}"


def _memory_failure_code(exc: Exception) -> ExecutionFailureCode:
    if isinstance(exc, StoredRuleParseError):
        return ExecutionFailureCode.STORED_RULE_PARSE_FAILURE
    if isinstance(exc, RuleMemoryRecoveryRequiredError):
        return ExecutionFailureCode.RULE_MEMORY_RECOVERY_REQUIRED
    if isinstance(exc, RuleMemoryRecoveryError):
        return ExecutionFailureCode.RULE_MEMORY_RECOVERY_FAILURE
    if isinstance(exc, RuleMemoryIOError):
        return ExecutionFailureCode.EXECUTION_IO_FAILURE
    return ExecutionFailureCode.RULE_MEMORY_INTEGRITY_FAILURE
