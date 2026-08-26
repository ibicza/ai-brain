"""Immutable authority-aware routing and bounded-tool artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ai_brain.stage2.router.version import (
    ROUTE_RECEIPT_SCHEMA_VERSION,
    TOOL_REGISTRY_SCHEMA_VERSION,
    UNIFIED_ROUTER_SCHEMA_VERSION,
)


class RequestSourceKind(StrEnum):
    STRUCTURED_FACT = "STRUCTURED_FACT"
    STRUCTURED_SKILL = "STRUCTURED_SKILL"
    STRUCTURED_TOOL = "STRUCTURED_TOOL"
    CONTROLLED_LANGUAGE = "CONTROLLED_LANGUAGE"
    ASSISTIVE_TEXT = "ASSISTIVE_TEXT"


class RouteTarget(StrEnum):
    FACT_QUERY = "FACT_QUERY"
    SKILL_REQUEST = "SKILL_REQUEST"
    TOOL_REQUEST = "TOOL_REQUEST"
    CLARIFICATION = "CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"
    COMPOSITE_REQUIRED = "COMPOSITE_REQUIRED"


class RouteAuthority(StrEnum):
    EXACT_STRUCTURED = "EXACT_STRUCTURED"
    EXACT_CONTROLLED = "EXACT_CONTROLLED"
    ASSISTIVE_PROPOSAL = "ASSISTIVE_PROPOSAL"


class RouteStatus(StrEnum):
    EXACT_ROUTE = "EXACT_ROUTE"
    ASSISTIVE_CANDIDATES = "ASSISTIVE_CANDIDATES"
    AMBIGUOUS_ROUTE = "AMBIGUOUS_ROUTE"
    UNSUPPORTED_ROUTE = "UNSUPPORTED_ROUTE"
    COMPOSITE_ROUTE = "COMPOSITE_ROUTE"
    STALE_DEPENDENCY = "STALE_DEPENDENCY"
    INVALID_REQUEST = "INVALID_REQUEST"


class NextAction(StrEnum):
    ANSWER_FACT = "ANSWER_FACT"
    REVIEW_FACT_CONFLICT = "REVIEW_FACT_CONFLICT"
    CONFIRM_SKILL = "CONFIRM_SKILL"
    REVIEW_SKILL_CANDIDATES = "REVIEW_SKILL_CANDIDATES"
    CONFIRM_TOOL = "CONFIRM_TOOL"
    REVIEW_TOOL_CANDIDATES = "REVIEW_TOOL_CANDIDATES"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    SPLIT_REQUEST_MANUALLY = "SPLIT_REQUEST_MANUALLY"
    REVIEW_ROUTE = "REVIEW_ROUTE"
    NO_ACTION = "NO_ACTION"


class ClarificationKind(StrEnum):
    FACT_OR_SKILL = "FACT_OR_SKILL"
    FACT_OR_TOOL = "FACT_OR_TOOL"
    SKILL_OR_TOOL = "SKILL_OR_TOOL"
    MULTIPLE_FACT_ENTITIES = "MULTIPLE_FACT_ENTITIES"
    UNKNOWN_FACT_PREDICATE = "UNKNOWN_FACT_PREDICATE"
    MISSING_SKILL_DESTINATION = "MISSING_SKILL_DESTINATION"
    MISSING_TOOL_ARGUMENT = "MISSING_TOOL_ARGUMENT"
    MULTI_INTENT = "MULTI_INTENT"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"


class ToolExecutionClass(StrEnum):
    PURE_LOCAL_READ_ONLY = "PURE_LOCAL_READ_ONLY"
    EXTERNAL_READ_ONLY = "EXTERNAL_READ_ONLY"
    SIDE_EFFECTING = "SIDE_EFFECTING"


class ToolApprovalPolicy(StrEnum):
    EXPLICIT_CONFIRMATION = "EXPLICIT_CONFIRMATION"
    UNAVAILABLE = "UNAVAILABLE"


class ToolExecutionStatus(StrEnum):
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    TOOL_REQUIRES_FUTURE_INTEGRATION = "TOOL_REQUIRES_FUTURE_INTEGRATION"
    STALE_DEPENDENCY = "STALE_DEPENDENCY"


class ConfirmationDecision(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ReplayStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"


@dataclass(frozen=True)
class RequestEnvelope:
    request_id: str
    source_kind: RequestSourceKind
    original_input: str
    original_input_hash: str
    semantic_input_hash: str
    language: str | None
    structured_payload: dict[str, Any] | None
    requested_valid_at: str | None
    requested_known_at: str | None
    requested_equivalence_scope: str | None
    created_at: str
    schema_version: int
    request_hash: str


@dataclass(frozen=True)
class DependencySnapshot:
    fact_memory_hash: str | None
    skill_registry_hash: str | None
    rule_memory_hash: str | None
    tool_registry_hash: str
    stage1_version: str
    stage2_schema_version: int
    fact_memory_schema_version: int
    unified_router_schema_version: int = UNIFIED_ROUTER_SCHEMA_VERSION


@dataclass(frozen=True)
class RouteDecision:
    route_id: str
    request_id: str
    request_hash: str
    selected_target: RouteTarget
    route_status: RouteStatus
    route_authority: RouteAuthority
    exact_match: bool
    candidate_targets: tuple[RouteTarget, ...]
    parser_evidence: dict[str, Any]
    ambiguity_fields: tuple[str, ...]
    required_next_action: NextAction
    dependencies: DependencySnapshot
    created_at: str
    route_decision_hash: str


@dataclass(frozen=True)
class ClarificationRequest:
    clarification_id: str
    request_id: str
    route_decision_hash: str
    kind: ClarificationKind
    missing_field: str
    question_ru: str
    question_en: str
    round_number: int
    created_at: str
    clarification_hash: str


@dataclass(frozen=True)
class RouteReceipt:
    receipt_id: str
    request_id: str
    request_hash: str
    route_decision_hash: str
    selected_target: RouteTarget
    route_authority: RouteAuthority
    exact_parser_evidence_hash: str
    dependency_hash: str
    clarification_hash: str | None
    confirmer_identity: str | None
    confirmer_identity_type: str | None
    created_at: str
    schema_version: int = ROUTE_RECEIPT_SCHEMA_VERSION
    receipt_hash: str = ""


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    version: int
    canonical_name_ru: str
    canonical_name_en: str
    aliases_ru: tuple[str, ...]
    aliases_en: tuple[str, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    execution_class: ToolExecutionClass
    deterministic: bool
    network_required: bool
    approval_policy: ToolApprovalPolicy
    implementation_hash: str
    active: bool
    deprecated: bool
    created_at: str
    descriptor_hash: str
    schema_version: int = TOOL_REGISTRY_SCHEMA_VERSION


@dataclass(frozen=True)
class ToolCallProposal:
    proposal_id: str
    request_id: str
    request_hash: str
    route_decision_hash: str
    tool_id: str
    tool_version: int
    typed_arguments: dict[str, Any]
    argument_hash: str
    tool_implementation_hash: str
    tool_registry_hash: str
    confirmation_required: bool
    created_at: str
    proposal_hash: str


@dataclass(frozen=True)
class ToolCallConfirmation:
    confirmation_id: str
    proposal_hash: str
    request_hash: str
    route_decision_hash: str
    tool_registry_hash: str
    argument_hash: str
    decision: ConfirmationDecision
    confirmer_identity: str
    confirmer_identity_type: str
    created_at: str
    confirmation_hash: str


@dataclass(frozen=True)
class ToolResultBundle:
    result_id: str
    request_id: str
    request_hash: str
    route_decision_hash: str
    proposal_hash: str
    confirmation_hash: str
    tool_id: str
    tool_version: int
    tool_implementation_hash: str
    tool_registry_hash: str
    argument_hash: str
    status: ToolExecutionStatus
    output: dict[str, Any]
    executed_at: str
    result_hash: str


@dataclass(frozen=True)
class UnifiedResponseEnvelope:
    response_id: str
    request_id: str
    request_hash: str
    route_decision_hash: str
    route_target: RouteTarget
    route_authority: RouteAuthority
    route_status: RouteStatus
    fact_answer_hash: str | None = None
    skill_selection_hash: str | None = None
    skill_dispatch_hash: str | None = None
    tool_proposal_hash: str | None = None
    tool_result_hash: str | None = None
    clarification_hash: str | None = None
    warnings: tuple[str, ...] = ()
    dependency_snapshots: dict[str, str | int | None] = field(default_factory=dict)
    created_at: str = ""
    response_hash: str = ""

    def __post_init__(self) -> None:
        authorities = (
            self.fact_answer_hash is not None,
            self.skill_selection_hash is not None
            or self.skill_dispatch_hash is not None,
            self.tool_proposal_hash is not None or self.tool_result_hash is not None,
        )
        if sum(authorities) > 1:
            raise ValueError("unified response contains multiple authority domains")
        if self.route_target == RouteTarget.COMPOSITE_REQUIRED and any(authorities):
            raise ValueError("composite response cannot contain an executed payload")
