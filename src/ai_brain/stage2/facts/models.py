"""Immutable factual-memory records and workflow artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.facts.version import FACT_MEMORY_SCHEMA_VERSION


class EntityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class EntityResolutionStatus(StrEnum):
    EXACT = "EXACT"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"


class Cardinality(StrEnum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"


class TemporalMode(StrEnum):
    ATEMPORAL = "ATEMPORAL"
    VALID_INTERVAL = "VALID_INTERVAL"
    EVENT = "EVENT"


class SourceKind(StrEnum):
    OFFICIAL_PRIMARY = "OFFICIAL_PRIMARY"
    ACADEMIC_PRIMARY = "ACADEMIC_PRIMARY"
    REFERENCE = "REFERENCE"
    LOCAL_DOCUMENT = "LOCAL_DOCUMENT"
    USER_ASSERTION = "USER_ASSERTION"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    MODEL_INFERENCE = "MODEL_INFERENCE"


class SourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETRACTED = "RETRACTED"
    UNAVAILABLE = "UNAVAILABLE"


class ActorIdentityType(StrEnum):
    HUMAN = "HUMAN"
    TRUSTED_PROCESS = "TRUSTED_PROCESS"
    MODEL = "MODEL"


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"


class EvidenceLocationKind(StrEnum):
    CHAR_SPAN = "CHAR_SPAN"
    BYTE_SPAN = "BYTE_SPAN"
    JSON_POINTER = "JSON_POINTER"


class ExtractionMethod(StrEnum):
    MANUAL = "MANUAL"
    DETERMINISTIC = "DETERMINISTIC"
    MODEL_PROPOSED = "MODEL_PROPOSED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ClaimStatus(StrEnum):
    PROPOSED = "PROPOSED"
    SUPPORTED = "SUPPORTED"
    CORROBORATED = "CORROBORATED"
    CONTESTED = "CONTESTED"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    REJECTED = "REJECTED"


class ProposalSource(StrEnum):
    STRUCTURED_JSON = "STRUCTURED_JSON"
    MANUAL_FORM = "MANUAL_FORM"
    LOCAL_DOCUMENT_EXTRACTION = "LOCAL_DOCUMENT_EXTRACTION"
    MODEL_EXTRACTION = "MODEL_EXTRACTION"


class ProposalStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PARSED = "PARSED"
    EVIDENCE_ATTACHED = "EVIDENCE_ATTACHED"
    VALIDATED = "VALIDATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    UNSUPPORTED_PREDICATE = "UNSUPPORTED_PREDICATE"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT = "EDIT"
    MARK_CONTESTED = "MARK_CONTESTED"
    ASK_FOR_SOURCE = "ASK_FOR_SOURCE"


class ConflictResolutionStatus(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"


class ConflictResolutionKind(StrEnum):
    INITIAL_STATE = "INITIAL_STATE"
    CLAIM_RETRACTED = "CLAIM_RETRACTED"
    CLAIM_SUPERSEDED = "CLAIM_SUPERSEDED"
    MANUAL_RESOLUTION = "MANUAL_RESOLUTION"
    DISMISSED_AS_NOT_CONFLICTING = "DISMISSED_AS_NOT_CONFLICTING"


class ResolutionEvidenceRole(StrEnum):
    SUPPORTS_REMAINING = "SUPPORTS_REMAINING"
    CONTRADICTS_REMOVED = "CONTRADICTS_REMOVED"
    SUPPORTS_DISMISSAL = "SUPPORTS_DISMISSAL"


class EvidenceConflictState(StrEnum):
    CLEAR = "CLEAR"
    CONTESTED = "CONTESTED"


class ProvenanceDetailMode(StrEnum):
    FULL = "FULL"
    REFERENCES_ONLY = "REFERENCES_ONLY"


class QueryStatus(StrEnum):
    EXACT_SINGLE = "EXACT_SINGLE"
    EXACT_MULTI = "EXACT_MULTI"
    CONFLICT = "CONFLICT"
    NO_FACT = "NO_FACT"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"
    UNKNOWN_PREDICATE = "UNKNOWN_PREDICATE"
    STALE_ONLY = "STALE_ONLY"
    RETRACTED_ONLY = "RETRACTED_ONLY"
    INVALID_QUERY = "INVALID_QUERY"


class ReplayStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    entity_type: str
    canonical_label_ru: str
    canonical_label_en: str
    aliases_ru: tuple[str, ...]
    aliases_en: tuple[str, ...]
    external_identifiers: dict[str, str]
    status: EntityStatus
    created_at: str
    updated_at: str
    provenance: tuple[dict[str, Any], ...]
    content_hash: str
    schema_version: int = FACT_MEMORY_SCHEMA_VERSION


@dataclass(frozen=True)
class EntityResolution:
    status: EntityResolutionStatus
    entity_ids: tuple[str, ...]
    normalized_input: str


@dataclass(frozen=True)
class PredicateDefinition:
    predicate_id: str
    canonical_name_ru: str
    canonical_name_en: str
    subject_entity_type: str
    object_kind: FactValueKind
    cardinality: Cardinality
    temporal_mode: TemporalMode
    allowed_qualifiers: dict[str, FactValueKind]
    unit_dimension: str | None
    conflict_key_fields: tuple[str, ...]
    overlapping_intervals_permitted: bool
    schema_version: int
    active: bool
    deprecated: bool
    content_hash: str


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_kind: SourceKind
    title: str
    author: str | None
    publisher: str | None
    locator: str | None
    published_at: str | None
    retrieved_at: str
    language: str | None
    source_family: str
    trust_tier: str
    content_hash: str
    snapshot_hash: str
    status: SourceStatus
    license_metadata: dict[str, Any]
    original_filename: str | None
    media_type: str
    created_at: str
    record_hash: str


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_id: str
    relation: EvidenceRelation
    snapshot_hash: str
    location_kind: EvidenceLocationKind
    location: dict[str, Any]
    excerpt_hash: str
    extraction_method: ExtractionMethod
    extraction_confidence: str
    reviewer: str | None
    reviewer_identity_type: ActorIdentityType | None
    approval_status: ApprovalStatus
    created_at: str
    evidence_hash: str


@dataclass(frozen=True)
class FactProposal:
    proposal_id: str
    revision: int
    source: ProposalSource
    status: ProposalStatus
    subject_entity_id: str
    predicate_id: str
    object_value: FactValue
    qualifiers: dict[str, FactValue]
    valid_from: str | None
    valid_to: str | None
    source_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    reviewer_identity: str | None
    reviewer_identity_type: ActorIdentityType | None
    created_at: str
    updated_at: str
    proposal_hash: str
    schema_version: int = FACT_MEMORY_SCHEMA_VERSION


@dataclass(frozen=True)
class FactApprovalEnvelope:
    approval_id: str
    proposal_id: str
    proposal_hash: str
    entity_hash: str
    predicate_definition_hash: str
    typed_value_hash: str
    qualifier_hash: str
    valid_from: str | None
    valid_to: str | None
    source_hashes: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    reviewer_identity: str
    reviewer_identity_type: ActorIdentityType
    supporting_evidence_hashes: tuple[str, ...]
    independent_non_model_support: bool
    decision: ApprovalDecision
    contested_approval: bool
    policy_version: str
    fact_memory_schema_version: int
    created_at: str
    approval_hash: str


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    subject_entity_id: str
    predicate_id: str
    object_value: FactValue
    qualifiers: dict[str, FactValue]
    valid_from: str | None
    valid_to: str | None
    recorded_at: str
    status: ClaimStatus
    evidence_ids: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    source_family_support_set: tuple[str, ...]
    source_family_contradiction_set: tuple[str, ...]
    supersedes_claim_ids: tuple[str, ...]
    retraction_reason: str | None
    proposal_hash: str
    approval_hash: str
    canonical_claim_hash: str
    claim_record_hash: str
    schema_version: int = FACT_MEMORY_SCHEMA_VERSION


@dataclass(frozen=True)
class ConflictGroup:
    conflict_group_id: str
    claim_ids: tuple[str, ...]
    subject_entity_id: str
    predicate_id: str
    overlapping_interval: tuple[str | None, str | None]
    conflict_reason: str
    resolution_status: ConflictResolutionStatus
    created_at: str
    resolved_at: str | None
    resolution_evidence_ids: tuple[str, ...]
    group_hash: str


@dataclass(frozen=True)
class ConflictResolutionEvent:
    event_id: str
    conflict_group_id: str
    prior_status: ConflictResolutionStatus
    new_status: ConflictResolutionStatus
    resolution_kind: ConflictResolutionKind
    selected_claim_ids: tuple[str, ...]
    remaining_claim_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    actor_identity: str
    actor_identity_type: ActorIdentityType
    reason: str
    recorded_at: str
    event_hash: str
    evidence_links: tuple[ResolutionEvidenceLink, ...] = ()


@dataclass(frozen=True)
class ResolutionEvidenceLink:
    evidence_id: str
    claim_id: str
    role: ResolutionEvidenceRole
    link_hash: str


@dataclass(frozen=True)
class TransactionIntervalState:
    claim_id: str
    transaction_from: str
    transaction_to: str | None
    status: ClaimStatus
    known_at: str
    status_event_hash: str | None


@dataclass(frozen=True)
class ClaimState:
    record: ClaimRecord
    status: ClaimStatus
    transaction: TransactionIntervalState
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    evidence_conflict_state: EvidenceConflictState


@dataclass(frozen=True)
class SourceState:
    record: SourceRecord
    status: SourceStatus
    known_at: str
    status_event_hash: str | None


@dataclass(frozen=True)
class FactQuery:
    query_id: str
    subject: str
    predicate_id: str | None
    object_filter: FactValue | None = None
    qualifier_filters: dict[str, FactValue] = field(default_factory=dict)
    valid_at: str | None = None
    known_at: str | None = None
    known_at_explicitly_requested: bool = False
    accepted_statuses: tuple[ClaimStatus, ...] = (
        ClaimStatus.SUPPORTED,
        ClaimStatus.CORROBORATED,
        ClaimStatus.CONTESTED,
    )
    include_conflicts: bool = True
    include_retracted: bool = False
    include_evidence: bool = True
    language: str = "en"
    memory_snapshot: str | None = None
    created_at: str = ""
    query_hash: str = ""


@dataclass(frozen=True)
class ClaimAnswer:
    claim_id: str
    claim_hash: str
    value: FactValue
    status: ClaimStatus
    valid_from: str | None
    valid_to: str | None
    recorded_at: str
    transaction_to: str | None
    transaction_status_as_known_at: ClaimStatus
    known_at: str
    supporting_evidence_ids: tuple[str, ...]
    supporting_evidence_hashes: tuple[str, ...]
    supporting_source_ids: tuple[str, ...]
    supporting_source_hashes: tuple[str, ...]
    supporting_source_citations: tuple[dict[str, Any], ...]
    supporting_source_trust_tiers: tuple[str, ...]
    independent_supporting_source_family_count: int
    contradicting_evidence_ids: tuple[str, ...]
    contradicting_evidence_hashes: tuple[str, ...]
    contradicting_source_ids: tuple[str, ...]
    contradicting_source_hashes: tuple[str, ...]
    contradicting_source_citations: tuple[dict[str, Any], ...]
    contradicting_source_trust_tiers: tuple[str, ...]
    independent_contradicting_source_family_count: int
    support_freshness_state: str
    contradiction_freshness_state: str
    evidence_conflict_state: EvidenceConflictState
    source_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    source_citations: tuple[dict[str, Any], ...]
    evidence_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_trust_tiers: tuple[str, ...]
    independent_source_family_count: int
    evidence_count: int
    freshness_state: str
    review_state: str
    conflict_state: str
    source_retraction_state: str


@dataclass(frozen=True)
class FactAnswerBundle:
    query_id: str
    query_hash: str
    fact_memory_schema_version: int
    answer_schema_version: int
    memory_snapshot_hash: str
    valid_at: str | None
    known_at: str
    answer_status: QueryStatus
    selected_claim_ids: tuple[str, ...]
    conflict_group_ids: tuple[str, ...]
    conflict_resolution_statuses: tuple[tuple[str, ConflictResolutionStatus], ...]
    claims: tuple[ClaimAnswer, ...]
    provenance_detail_mode: ProvenanceDetailMode
    warnings: tuple[str, ...]
    generated_at: str
    rendering_version: str
    answer_hash: str
