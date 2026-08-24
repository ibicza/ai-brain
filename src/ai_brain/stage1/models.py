"""Immutable production workflow models and canonical hashing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.version import STAGE1_VERSION

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

    def __post_init__(self) -> None:
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
            ProposalStatus.VERIFIED: {ProposalStatus.APPROVED, ProposalStatus.EDITED},
            ProposalStatus.APPROVED: {ProposalStatus.INSTALLED},
            ProposalStatus.INSTALLED: {ProposalStatus.EXECUTED},
            ProposalStatus.EXECUTED: {ProposalStatus.EXECUTED},
        }
        if status not in allowed.get(self.status, set()):
            raise ValueError(f"Invalid proposal transition {self.status} -> {status}")
        return replace(self, status=status, **changes)


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
    stage1_version: str = STAGE1_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", ApprovalDecision(self.decision))
        if not self.identity.strip():
            raise ValueError("approval identity is required")
        if self.identity_type not in {"USER", "TRUSTED_SUPERVISOR"}:
            raise ValueError("identity_type must be USER or TRUSTED_SUPERVISOR")
        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError as exc:
            raise ValueError("approval timestamp must be ISO-8601") from exc


@dataclass(frozen=True)
class ExecutionResult:
    rule_id: str
    initial_state: dict[str, int]
    final_state: dict[str, int]
    actions: tuple[str, ...]
    execution_hash: str
    proposal_id: str | None = None


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
        default=lambda item: asdict(item) if is_dataclass(item) else str(item),
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def specification_hash(specification: ProgramSpecification) -> str:
    return content_hash(specification)


def proposal_hash(proposal: RuleProposal) -> str:
    # Workflow-only status changes must not stale a valid content-bound approval;
    # edits increment revision and alter specification/provenance.
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
        }
    )
