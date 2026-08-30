from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage3.knowledge_ir.records import (
    EpistemicCharacter,
    KnowledgeContent,
    KnowledgeKind,
)


class SourceMediaType(StrEnum):
    TEXT = "text/plain"
    MARKDOWN = "text/markdown"
    HTML = "text/html"
    JSON = "application/json"
    PDF = "application/pdf"
    JAVADOC_HTML = "text/x-javadoc-html"
    JAVA_SOURCE = "text/x-java-source"


class SegmentKind(StrEnum):
    DOCUMENT = "DOCUMENT"
    SECTION = "SECTION"
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST = "LIST"
    TABLE = "TABLE"
    DEFINITION_BLOCK = "DEFINITION_BLOCK"
    EQUATION_BLOCK = "EQUATION_BLOCK"
    CODE_BLOCK = "CODE_BLOCK"
    API_SIGNATURE = "API_SIGNATURE"
    EXAMPLE_BLOCK = "EXAMPLE_BLOCK"
    TEST_BLOCK = "TEST_BLOCK"
    NOTE = "NOTE"
    WARNING = "WARNING"


class ExtractionMethod(StrEnum):
    JAVA_AST = "JAVA_AST"
    DETERMINISTIC_STRUCTURED = "DETERMINISTIC_STRUCTURED"
    DETERMINISTIC_PATTERN = "DETERMINISTIC_PATTERN"
    REVIEWED_MAPPING = "REVIEWED_MAPPING"
    ASSISTIVE_MODEL_PROPOSAL = "ASSISTIVE_MODEL_PROPOSAL"


class ProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    VERIFIED = "VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFLICT = "CONFLICT"
    NEEDS_NEW_CAPABILITY = "NEEDS_NEW_CAPABILITY"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT_AND_APPROVE = "EDIT_AND_APPROVE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NEEDS_NEW_CAPABILITY = "NEEDS_NEW_CAPABILITY"


class ClarificationKind(StrEnum):
    UNDECLARED_VARIABLE = "UNDECLARED_VARIABLE"
    AMBIGUOUS_SYMBOL = "AMBIGUOUS_SYMBOL"
    MISSING_UNIT = "MISSING_UNIT"
    MISSING_APPLICABILITY = "MISSING_APPLICABILITY"
    UNCLEAR_ENTITY = "UNCLEAR_ENTITY"
    CONFLICTING_DEFINITION = "CONFLICTING_DEFINITION"
    UNKNOWN_EXCEPTION_SCOPE = "UNKNOWN_EXCEPTION_SCOPE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    UNCERTAIN_EPISTEMIC = "UNCERTAIN_EPISTEMIC"


@dataclass(frozen=True)
class SourceLocation:
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int
    heading_path: tuple[str, ...]
    table_row: int | None = None
    table_cell: int | None = None
    page: int | None = None


@dataclass(frozen=True)
class DocumentStructure:
    heading_count: int
    table_count: int
    code_block_count: int
    page_count: int | None
    structure_hash: str


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    media_type: SourceMediaType
    language: str
    relative_path: str
    bytes_hash: str
    canonical_text_hash: str
    source_metadata: tuple[tuple[str, str], ...]
    imported_at: str
    version: str
    parent_bundle_id: str
    structure: DocumentStructure
    document_hash: str


@dataclass(frozen=True)
class AcquisitionManifest:
    compiler_version: str
    resource_policy_hash: str
    runtime_network: bool
    document_hashes: tuple[str, ...]
    schema_version: int
    manifest_hash: str


@dataclass(frozen=True)
class SourceBundle:
    bundle_id: str
    domain_tags: tuple[str, ...]
    documents: tuple[SourceDocument, ...]
    manifest: AcquisitionManifest
    created_at: str
    bundle_hash: str


@dataclass(frozen=True)
class SourceSegment:
    segment_id: str
    bundle_id: str
    document_id: str
    kind: SegmentKind
    ordinal: int
    canonical_text: str
    source_location: SourceLocation
    source_span_hash: str
    segment_hash: str


@dataclass(frozen=True)
class KnowledgeProposal:
    proposal_id: str
    source_bundle_id: str
    segment_ids: tuple[str, ...]
    proposed_kind: KnowledgeKind
    proposed_epistemic_character: EpistemicCharacter
    proposed_content: KnowledgeContent
    proposed_dependencies: tuple[str, ...]
    proposed_applicability: tuple[str, ...]
    proposed_capabilities: tuple[str, ...]
    extraction_method: ExtractionMethod
    status: ProposalStatus
    ambiguity_fields: tuple[str, ...]
    compiler_version: str
    schema_version: int
    proposal_hash: str


@dataclass(frozen=True)
class ClarificationQuestion:
    clarification_id: str
    proposal_id: str
    kind: ClarificationKind
    exact_field: str
    question: str
    source_segment_ids: tuple[str, ...]
    clarification_hash: str


@dataclass(frozen=True)
class ClarificationAnswer:
    clarification_id: str
    answer: str
    reviewer_identity: str
    reviewer_type: ActorIdentityType
    timestamp: str
    answer_hash: str


@dataclass(frozen=True)
class ConflictArtifact:
    conflict_id: str
    proposal_ids: tuple[str, ...]
    source_segment_ids: tuple[str, ...]
    conflict_kind: str
    exact_field: str
    conflict_hash: str


@dataclass(frozen=True)
class AcquisitionReview:
    review_id: str
    proposal_hash: str
    reviewer_identity: str
    reviewer_type: ActorIdentityType
    decision: ReviewDecision
    edited_content_hash: str | None
    rationale: str
    timestamp: str
    schema_version: int
    review_hash: str


@dataclass(frozen=True)
class ProposalApproval:
    proposal_id: str
    original_proposal_hash: str
    approved_proposal_hash: str
    review_hash: str
    approval_hash: str
