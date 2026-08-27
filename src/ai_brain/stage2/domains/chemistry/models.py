"""Immutable artifacts for bounded introductory chemistry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AtomicWeightKind(StrEnum):
    SINGLE = "SINGLE"
    INTERVAL = "INTERVAL"
    CONVENTIONAL = "CONVENTIONAL"
    NO_STANDARD_VALUE = "NO_STANDARD_VALUE"


class AtomicWeightRequest(StrEnum):
    STANDARD = "STANDARD"
    ABRIDGED = "ABRIDGED"
    ALL = "ALL"


class AtomicWeightMode(StrEnum):
    CONVENTIONAL_CLASSROOM = "CONVENTIONAL_CLASSROOM"
    NATURAL_VARIABILITY_ENVELOPE = "NATURAL_VARIABILITY_ENVELOPE"


class EntityAmountDirection(StrEnum):
    MOLES_TO_ENTITIES = "MOLES_TO_ENTITIES"
    ENTITIES_TO_MOLES = "ENTITIES_TO_MOLES"


class EntityAmountBasis(StrEnum):
    FORMULA_ENTITIES = "FORMULA_ENTITIES"
    TOTAL_ATOMS_IN_FORMULA = "TOTAL_ATOMS_IN_FORMULA"
    ATOMS_OF_ELEMENT_IN_FORMULA = "ATOMS_OF_ELEMENT_IN_FORMULA"


class ChemistryReplayStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE_FACT_MEMORY = "STALE_FACT_MEMORY"
    STALE_ELEMENT_CLAIM = "STALE_ELEMENT_CLAIM"
    RETRACTED_ELEMENT_CLAIM = "RETRACTED_ELEMENT_CLAIM"
    SUPERSEDED_ELEMENT_CLAIM = "SUPERSEDED_ELEMENT_CLAIM"
    CONFLICTING_ATOMIC_WEIGHT = "CONFLICTING_ATOMIC_WEIGHT"
    CONTRADICTING_EVIDENCE = "CONTRADICTING_EVIDENCE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    STALE_SOURCE = "STALE_SOURCE"
    RETRACTED_SOURCE = "RETRACTED_SOURCE"
    STALE_DERIVATION_CHAIN = "STALE_DERIVATION_CHAIN"
    RETRACTED_UPSTREAM_SOURCE = "RETRACTED_UPSTREAM_SOURCE"
    UNAVAILABLE_UPSTREAM_SOURCE = "UNAVAILABLE_UPSTREAM_SOURCE"
    STALE_UPSTREAM_SOURCE = "STALE_UPSTREAM_SOURCE"
    STALE_DERIVED_SOURCE = "STALE_DERIVED_SOURCE"
    DERIVATION_SOURCE_MISMATCH = "DERIVATION_SOURCE_MISMATCH"
    DERIVATION_CONTENT_MISMATCH = "DERIVATION_CONTENT_MISMATCH"
    DERIVATION_METHOD_CHANGED = "DERIVATION_METHOD_CHANGED"
    STALE_EXTRACTION_POLICY = "STALE_EXTRACTION_POLICY"
    STALE_SOURCE_CHAIN = "STALE_SOURCE_CHAIN"
    STALE_DOMAIN_MANIFEST = "STALE_DOMAIN_MANIFEST"
    STALE_ATOMIC_WEIGHT_POLICY = "STALE_ATOMIC_WEIGHT_POLICY"
    STALE_ROUNDING_POLICY = "STALE_ROUNDING_POLICY"
    STALE_FORMULA_GRAMMAR = "STALE_FORMULA_GRAMMAR"
    STALE_TOOL_IMPLEMENTATION = "STALE_TOOL_IMPLEMENTATION"
    INCOMPATIBLE_DOMAIN_VERSION = "INCOMPATIBLE_DOMAIN_VERSION"
    INVALID_RESULT = "INVALID_RESULT"


@dataclass(frozen=True)
class FormulaLimits:
    max_input_chars: int = 256
    max_nesting_depth: int = 4
    max_group_count: int = 64
    max_element_terms: int = 128
    max_distinct_elements: int = 32
    max_subscript: int = 1_000_000
    max_total_atoms: int = 10_000_000
    max_canonical_output_chars: int = 512


@dataclass(frozen=True)
class ChemistryQuantityLimits:
    max_raw_chars: int = 512
    max_coefficient_digits: int = 128
    max_absolute_exponent: int = 256
    max_scale: int = 256
    max_adjusted_exponent: int = 256
    max_rendered_chars: int = 512
    max_result_digits: int = 128
    context_precision: int = 120
    max_quantity_abs: str = "1e100"
    max_integer_bits: int = 4096


@dataclass(frozen=True)
class ChemistryRoundingSpec:
    significant_digits: int = 6
    rounding_mode: str = "ROUND_HALF_EVEN"
    scientific_notation_threshold: int = 12
    trailing_zero_policy: str = "PRESERVE_SIGNIFICANCE"
    policy_version: str = "2.0"


class DerivationMethod(StrEnum):
    DETERMINISTIC_EXTRACTION = "DETERMINISTIC_EXTRACTION"
    REVIEWED_MANUAL_MAPPING = "REVIEWED_MANUAL_MAPPING"
    POLICY_TRANSFORMATION = "POLICY_TRANSFORMATION"


@dataclass(frozen=True)
class UpstreamSourceReference:
    source_id: str
    source_kind: str
    snapshot_hash: str
    expected_source_record_hash: str | None
    source_family: str
    field_location_used: tuple[str, ...]
    reference_hash: str


@dataclass(frozen=True)
class FieldExtractionEvidence:
    output_field_name: str
    output_canonical_value: Any
    upstream_source_id: str
    upstream_snapshot_hash: str
    upstream_location_type: str
    upstream_locator: dict[str, Any]
    upstream_excerpt_hash: str | None
    extraction_method: DerivationMethod
    parser_mapping_implementation_hash: str
    reviewer: str | None
    evidence_hash: str


@dataclass(frozen=True)
class ManualSourceMappingApproval:
    approval_id: str
    official_source_id: str
    official_snapshot_hash: str
    selected_fields: tuple[dict[str, Any], ...]
    reviewer_identity: str
    reviewer_identity_type: str
    review_decision: str
    policy_version: str
    mapping_hash: str
    timestamp: str
    approval_hash: str


@dataclass(frozen=True)
class SourceDerivationRecordV2:
    derivation_id: str
    schema_version: int
    derivation_method: DerivationMethod
    derived_source_id: str
    derived_source_kind: str
    derived_media_type: str
    derived_file_path: str
    derived_file_byte_sha256: str
    derived_canonical_content_hash: str
    expected_source_snapshot_hash: str
    expected_source_record_hash: str | None
    upstream_sources: tuple[UpstreamSourceReference, ...]
    extractor_reviewer_identity: str
    extractor_implementation_manifest_hash: str
    extraction_policy_version: str
    field_level_mappings: tuple[FieldExtractionEvidence, ...]
    generated_at: str
    reviewed_at: str | None
    reviewer_identity: str | None
    reviewer_identity_type: str | None
    manual_mapping_approval_id: str | None
    manual_mapping_approval_hash: str | None
    derivation_hash: str


SourceDerivationRecord = SourceDerivationRecordV2


@dataclass(frozen=True)
class ElementTerm:
    symbol: str
    multiplier: int = 1


@dataclass(frozen=True)
class GroupTerm:
    terms: tuple[ElementTerm | GroupTerm, ...]
    multiplier: int = 1


@dataclass(frozen=True)
class CompositionEntry:
    symbol: str
    count: int


@dataclass(frozen=True)
class FormulaAst:
    terms: tuple[ElementTerm | GroupTerm, ...]
    composition: tuple[CompositionEntry, ...]
    canonical_formula: str
    original_input_hash: str
    grammar_version: str
    ast_hash: str


@dataclass(frozen=True)
class KnowledgeBinding:
    claim_id: str
    claim_record_hash: str
    claim_state_hash: str
    claim_status: str
    claim_status_event_hash: str | None
    evidence_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    evidence_relations: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_record_hashes: tuple[str, ...]
    source_state_hashes: tuple[str, ...]
    source_status_event_hashes: tuple[str | None, ...]
    derived_exact_file_hashes: tuple[str, ...]
    derived_canonical_content_hashes: tuple[str, ...]
    derivation_ids: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    derivation_methods: tuple[str, ...]
    upstream_source_ids: tuple[str, ...]
    upstream_source_record_hashes: tuple[str, ...]
    upstream_source_snapshot_hashes: tuple[str, ...]
    upstream_source_state_hashes: tuple[str, ...]
    upstream_status_event_hashes: tuple[str | None, ...]
    field_mapping_evidence_hashes: tuple[str, ...]
    binding_hash: str


@dataclass(frozen=True)
class AtomicWeightRecordV2:
    element_entity_id: str
    symbol: str
    atomic_number: int
    standard_kind: AtomicWeightKind
    standard_nominal: str | None
    standard_uncertainty: str | None
    standard_interval_lower: str | None
    standard_interval_upper: str | None
    standard_source_notation: str
    abridged_value: str
    abridged_uncertainty: str
    abridged_source_notation: str
    unit: str
    claim_ids: tuple[str, ...]
    claim_record_hashes: tuple[str, ...]
    claim_state_hashes: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_record_hashes: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    policy_version: str
    record_hash: str

    @property
    def conventional_value(self) -> str:
        return self.abridged_value

    @property
    def standard_value(self) -> str | None:
        return self.standard_nominal

    @property
    def interval_lower(self) -> str | None:
        return self.standard_interval_lower

    @property
    def interval_upper(self) -> str | None:
        return self.standard_interval_upper

    @property
    def claim_hashes(self) -> tuple[str, ...]:
        return self.claim_record_hashes

    @property
    def source_hashes(self) -> tuple[str, ...]:
        return self.source_record_hashes


AtomicWeightRecord = AtomicWeightRecordV2


@dataclass(frozen=True)
class AtomicWeightAnswerBundle:
    element_entity_id: str
    exact_symbol: str
    atomic_number: int
    standard_kind: AtomicWeightKind
    standard_nominal: str | None
    standard_uncertainty: str | None
    standard_interval_lower: str | None
    standard_interval_upper: str | None
    abridged_value: str
    abridged_uncertainty: str
    value_requested: AtomicWeightRequest
    source_record_hashes: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    fact_memory_snapshot_hash: str
    warnings: tuple[str, ...]
    answer_hash: str


@dataclass(frozen=True)
class ChemistryKnowledgeSnapshotV3:
    knowledge_snapshot_version: int
    domain_manifest_hash: str
    fact_memory_snapshot_hash: str
    atomic_weight_policy: str
    source_policy_version: str
    formula_grammar_version: str
    calculation_policy_version: str
    rounding_policy_hash: str
    element_records: tuple[AtomicWeightRecordV2, ...]
    source_chain_version: str
    source_chain_hash: str
    requirements: tuple[str, ...]
    avogadro_constant: str | None
    avogadro_claim_id: str | None
    avogadro_claim_record_hash: str | None
    avogadro_claim_state_hash: str | None
    avogadro_evidence_hashes: tuple[str, ...]
    avogadro_source_record_hashes: tuple[str, ...]
    bindings: tuple[KnowledgeBinding, ...]
    claim_ids: tuple[str, ...]
    claim_record_hashes: tuple[str, ...]
    claim_state_hashes: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_record_hashes: tuple[str, ...]
    source_state_hashes: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    derivation_ids: tuple[str, ...]
    derivation_methods: tuple[str, ...]
    upstream_source_ids: tuple[str, ...]
    upstream_source_record_hashes: tuple[str, ...]
    upstream_source_snapshot_hashes: tuple[str, ...]
    upstream_source_state_hashes: tuple[str, ...]
    upstream_status_event_hashes: tuple[str | None, ...]
    field_mapping_evidence_hashes: tuple[str, ...]
    created_at: str
    snapshot_hash: str

    @property
    def avogadro_claim_hash(self) -> str:
        return self.avogadro_claim_record_hash

    @property
    def avogadro_source_hashes(self) -> tuple[str, ...]:
        return self.avogadro_source_record_hashes

    @property
    def claim_hashes(self) -> tuple[str, ...]:
        return self.claim_record_hashes

    @property
    def source_hashes(self) -> tuple[str, ...]:
        return self.source_record_hashes


ChemistryKnowledgeSnapshot = ChemistryKnowledgeSnapshotV3
ChemistryKnowledgeSnapshotV2 = ChemistryKnowledgeSnapshotV3


@dataclass(frozen=True)
class ChemistryResultBundle:
    result_schema_version: int
    domain_version: str
    domain_manifest_hash: str
    operation: str
    formula: str | None
    formula_ast_hash: str | None
    composition_hash: str | None
    knowledge_snapshot_hash: str
    fact_memory_snapshot_hash: str
    claims_used: tuple[str, ...]
    claim_ids: tuple[str, ...]
    claim_state_hashes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    source_state_hashes: tuple[str, ...]
    derived_source_ids: tuple[str, ...]
    derived_source_record_hashes: tuple[str, ...]
    derived_source_snapshot_hashes: tuple[str, ...]
    derived_source_state_hashes: tuple[str, ...]
    derivation_ids: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    derivation_methods: tuple[str, ...]
    upstream_source_ids: tuple[str, ...]
    upstream_source_record_hashes: tuple[str, ...]
    upstream_source_snapshot_hashes: tuple[str, ...]
    upstream_source_state_hashes: tuple[str, ...]
    upstream_status_event_hashes: tuple[str | None, ...]
    field_mapping_evidence_hashes: tuple[str, ...]
    source_chain_version: str
    source_chain_hash: str
    calculation_steps: tuple[dict[str, Any], ...]
    result: dict[str, Any]
    warnings: tuple[str, ...]
    atomic_weight_policy: str
    formula_grammar_version: str
    calculation_policy_version: str
    rounding_policy: str
    rounding_policy_hash: str
    result_hash: str
