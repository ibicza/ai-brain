"""Immutable production workflow models and canonical hashing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.version import (
    EXECUTION_LIMITS_VERSION,
    STAGE1_VERSION,
    WORKFLOW_ARTIFACT_SCHEMA_VERSION,
)

VARIABLES = ("A", "B", "C", "D")
PRIMITIVES = ("MOVE_ONE", "DROP_ONE", "HALT")


class SourceKind(StrEnum):
    FORM = "FORM"
    CANONICAL_DSL = "CANONICAL_DSL"
    CONTROLLED_LANGUAGE = "CONTROLLED_LANGUAGE"


class ProposalStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PARSED = "PARSED"
    SUPPORTED_FOR_REVIEW = "SUPPORTED_FOR_REVIEW"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    CONTRADICTORY = "CONTRADICTORY"
    UNSUPPORTED = "UNSUPPORTED"
    EDITED = "EDITED"
    REVIEWED = "REVIEWED"
    VERIFIED = "VERIFIED"
    VERIFIED_REVIEWED = "VERIFIED_REVIEWED"
    APPROVED = "APPROVED"
    INSTALLED = "INSTALLED"
    EXECUTED = "EXECUTED"


class SemanticFamily(StrEnum):
    NOOP = "NOOP"
    CLEAR = "CLEAR"
    DRAIN = "DRAIN"
    MERGE_TWO = "MERGE_TWO"
    MERGE_THREE = "MERGE_THREE"
    DROP_THEN_TRANSFER = "DROP_THEN_TRANSFER"


class IssueCode(StrEnum):
    INVALID_SCHEMA = "INVALID_SCHEMA"
    MISSING_DESTINATION = "MISSING_DESTINATION"
    MISSING_PRESERVE_BEHAVIOR = "MISSING_PRESERVE_BEHAVIOR"
    MISSING_TERMINATION = "MISSING_TERMINATION"
    UNCLEAR_ORDER = "UNCLEAR_ORDER"
    AMBIGUOUS_PRONOUN = "AMBIGUOUS_PRONOUN"
    CONTRADICTION = "CONTRADICTION"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"


@dataclass(frozen=True)
class ProposalIssue:
    code: IssueCode
    field: str
    message: str


@dataclass(frozen=True)
class RuleProposal:
    proposal_id: str
    source_kind: SourceKind
    original_input: str
    language: str | None
    status: ProposalStatus
    specification: ProgramSpecification | None = None
    semantic_family: SemanticFamily | None = None
    issues: tuple[ProposalIssue, ...] = ()
    parser_name: str = ""
    parser_version: str = ""
    specification_hash: str | None = None
    provenance: tuple[dict[str, Any], ...] = ()
    created_at: str = ""
    revision: int = 1
    schema_version: int = WORKFLOW_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", SourceKind(self.source_kind))
        object.__setattr__(self, "status", ProposalStatus(self.status))
        if self.semantic_family is not None:
            object.__setattr__(
                self, "semantic_family", SemanticFamily(self.semantic_family)
            )
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(
            self, "provenance", tuple(dict(row) for row in self.provenance)
        )

    def transition(self, status: ProposalStatus, **changes: Any) -> RuleProposal:
        allowed = {
            ProposalStatus.RECEIVED: {ProposalStatus.PARSED},
            ProposalStatus.PARSED: {
                ProposalStatus.SUPPORTED_FOR_REVIEW,
                ProposalStatus.CLARIFICATION_REQUIRED,
                ProposalStatus.CONTRADICTORY,
                ProposalStatus.UNSUPPORTED,
            },
            ProposalStatus.CLARIFICATION_REQUIRED: {
                ProposalStatus.EDITED,
                ProposalStatus.CLARIFICATION_REQUIRED,
                ProposalStatus.CONTRADICTORY,
                ProposalStatus.UNSUPPORTED,
            },
            ProposalStatus.SUPPORTED_FOR_REVIEW: {
                ProposalStatus.EDITED,
                ProposalStatus.REVIEWED,
            },
            ProposalStatus.EDITED: {ProposalStatus.REVIEWED},
            ProposalStatus.REVIEWED: {ProposalStatus.VERIFIED, ProposalStatus.EDITED},
            ProposalStatus.VERIFIED: {
                ProposalStatus.VERIFIED_REVIEWED,
                ProposalStatus.EDITED,
            },
            ProposalStatus.VERIFIED_REVIEWED: {
                ProposalStatus.APPROVED,
                ProposalStatus.EDITED,
            },
            ProposalStatus.APPROVED: {ProposalStatus.INSTALLED},
            ProposalStatus.INSTALLED: {ProposalStatus.EXECUTED},
            ProposalStatus.EXECUTED: {ProposalStatus.EXECUTED},
        }
        actual = ProposalStatus(status)
        if actual not in allowed.get(self.status, set()):
            raise ValueError(f"Invalid proposal transition {self.status} -> {actual}")
        return replace(self, status=actual, **changes)


@dataclass(frozen=True)
class VerifiedCandidateBundle:
    proposal_id: str
    proposal_hash: str
    specification_hash: str
    candidate_dsl: str
    candidate_hash: str
    verification_status: str
    verification_evidence: dict[str, Any]
    evidence_hash: str
    compiler_name: str
    created_at: str
    schema_version: int = WORKFLOW_ARTIFACT_SCHEMA_VERSION


@dataclass(frozen=True)
class VerifiedReviewArtifact:
    proposal_id: str
    proposal_hash: str
    specification_hash: str
    original_input: str
    semantic_effect_summary: str
    changed_registers: tuple[str, ...]
    preserved_registers: tuple[str, ...]
    termination_condition: tuple[str, ...]
    ordered_phases: tuple[tuple[str, str, str | None], ...]
    compiler_name: str
    candidate_dsl: str
    candidate_hash: str
    static_verification_result: dict[str, Any]
    abstract_verification_result: dict[str, Any]
    property_verification_result: dict[str, Any]
    verification_evidence: dict[str, Any]
    evidence_hash: str
    stage1_version: str
    warnings: tuple[str, ...]
    created_at: str
    review_hash: str
    schema_version: int = WORKFLOW_ARTIFACT_SCHEMA_VERSION


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ApprovalEnvelope:
    decision: ApprovalDecision
    identity: str
    identity_type: str
    timestamp: str
    proposal_id: str
    proposal_hash: str
    specification_hash: str
    candidate_hash: str
    evidence_hash: str
    verified_review_hash: str
    stage1_version: str = STAGE1_VERSION
    schema_version: int = WORKFLOW_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", ApprovalDecision(self.decision))
        if not self.identity.strip():
            raise ValueError("approval identity is required")
        if self.identity_type not in {"USER", "TRUSTED_SUPERVISOR"}:
            raise ValueError("identity_type must be USER or TRUSTED_SUPERVISOR")
        parsed = datetime.fromisoformat(self.timestamp)
        if parsed.tzinfo is None:
            raise ValueError("approval timestamp must include a timezone")


@dataclass(frozen=True)
class InstalledRuleReceipt:
    proposal_id: str
    proposal_hash: str
    installed_rule_id: str
    rule_semantic_hash: str
    specification_hash: str
    candidate_hash: str
    evidence_hash: str
    verified_review_hash: str
    approval_hash: str
    rule_memory_schema_version: int
    stage1_version: str
    installation_timestamp: str
    schema_version: int = WORKFLOW_ARTIFACT_SCHEMA_VERSION


@dataclass(frozen=True)
class ExecutionLimits:
    max_register_value: int = 1_000_000
    max_total_units: int = 1_000_000
    max_execution_steps: int = 1_000_008
    max_trace_actions: int = 10_000
    capture_trace: bool = False
    fail_on_trace_overflow: bool = False
    version: str = EXECUTION_LIMITS_VERSION


class ExecutionFailureCode(StrEnum):
    INVALID_STATE = "INVALID_STATE"
    REGISTER_LIMIT_EXCEEDED = "REGISTER_LIMIT_EXCEEDED"
    TOTAL_LIMIT_EXCEEDED = "TOTAL_LIMIT_EXCEEDED"
    INVALID_LIMITS = "INVALID_LIMITS"
    STEP_LIMIT_EXCEEDED = "STEP_LIMIT_EXCEEDED"
    TRACE_LIMIT_EXCEEDED = "TRACE_LIMIT_EXCEEDED"
    INVALID_EXECUTION = "INVALID_EXECUTION"
    UNKNOWN_RULE = "UNKNOWN_RULE"
    RULE_NOT_ACTIVE = "RULE_NOT_ACTIVE"
    RULE_BINDING_MISMATCH = "RULE_BINDING_MISMATCH"


@dataclass(frozen=True)
class ExecutionResult:
    rule_id: str
    proposal_id: str
    initial_state: dict[str, int]
    final_state: dict[str, int] | None
    executed_steps: int
    halted: bool
    trace_requested: bool
    trace_truncated: bool
    captured_actions: tuple[str, ...]
    action_stream_hash: str
    execution_hash: str
    limits_version: str
    limits: dict[str, Any]
    failure_reason: str | None = None
    schema_version: int = WORKFLOW_ARTIFACT_SCHEMA_VERSION

    @property
    def actions(self) -> tuple[str, ...]:
        """Compatibility alias for v1.0.0 callers."""
        return self.captured_actions


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot canonicalize {type(value).__name__}")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def specification_hash(specification: ProgramSpecification) -> str:
    return content_hash(specification)


def proposal_hash(proposal: RuleProposal) -> str:
    # Workflow-only status changes do not stale content-bound review/approval;
    # edits increment revision and alter the specification/provenance.
    return content_hash(
        {
            "proposal_id": proposal.proposal_id,
            "source_kind": proposal.source_kind,
            "original_input": proposal.original_input,
            "language": proposal.language,
            "specification": proposal.specification,
            "semantic_family": proposal.semantic_family,
            "parser_name": proposal.parser_name,
            "parser_version": proposal.parser_version,
            "issues": proposal.issues,
            "provenance": proposal.provenance,
            "created_at": proposal.created_at,
            "revision": proposal.revision,
            "schema_version": proposal.schema_version,
        }
    )


def verified_review_content_hash(review: VerifiedReviewArtifact) -> str:
    row = asdict(review)
    row.pop("review_hash")
    return content_hash(row)


def approval_hash(approval: ApprovalEnvelope) -> str:
    return content_hash(approval)
