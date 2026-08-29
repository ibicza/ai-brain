from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CapabilityKind(StrEnum):
    FACT_RETRIEVAL = "FACT_RETRIEVAL"
    TEMPORAL_REASONING = "TEMPORAL_REASONING"
    SPATIAL_REASONING = "SPATIAL_REASONING"
    TAXONOMY_REASONING = "TAXONOMY_REASONING"
    QUANTITY_ARITHMETIC = "QUANTITY_ARITHMETIC"
    UNIT_CONVERSION = "UNIT_CONVERSION"
    EQUATION_EVALUATION = "EQUATION_EVALUATION"
    CONSTRAINT_VALIDATION = "CONSTRAINT_VALIDATION"
    PROCEDURE_EXECUTION = "PROCEDURE_EXECUTION"
    FORMULA_PARSING = "FORMULA_PARSING"
    CODE_PARSING = "CODE_PARSING"
    CODE_COMPILATION = "CODE_COMPILATION"
    TEST_EXECUTION = "TEST_EXECUTION"
    RENDERING = "RENDERING"
    GRADING = "GRADING"
    SOURCE_VERIFICATION = "SOURCE_VERIFICATION"


class ProviderType(StrEnum):
    TOOL = "TOOL"
    SKILL = "SKILL"
    PARSER = "PARSER"
    VERIFIER = "VERIFIER"
    SOLVER = "SOLVER"
    RENDERER = "RENDERER"
    CATALOG_COMPILER = "CATALOG_COMPILER"
    ADAPTER = "ADAPTER"


class AuthorityClass(StrEnum):
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    READ_ONLY_EXACT = "READ_ONLY_EXACT"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    OFFLINE_COMPILATION_ONLY = "OFFLINE_COMPILATION_ONLY"
    ASSISTIVE_ONLY = "ASSISTIVE_ONLY"


class CapabilityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    NEEDS_NEW_CAPABILITY = "NEEDS_NEW_CAPABILITY"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    version: str
    capability_kind: CapabilityKind
    canonical_name_ru: str
    canonical_name_en: str
    input_schema_hash: str
    output_schema_hash: str
    deterministic: bool
    authority_class: AuthorityClass
    provider_type: ProviderType
    provider_id: str
    provider_version: str
    provider_manifest_hash: str
    provider_implementation_hash: str
    required_capabilities: tuple[str, ...]
    allowed_execution_contexts: tuple[str, ...]
    resource_policy_hash: str
    status: CapabilityStatus
    descriptor_hash: str


@dataclass(frozen=True)
class CapabilityRequirement:
    capability_id: str
    version_range: str
    execution_context: str


@dataclass(frozen=True)
class CapabilityResolutionReceipt:
    requesting_domain_id: str
    requesting_pack_hash: str
    required_capability_id: str
    required_version_range: str
    selected_capability_version: str
    selected_descriptor_hash: str
    provider_id: str
    provider_version: str
    provider_manifest_hash: str
    provider_implementation_hash: str
    dependency_capabilities: tuple[str, ...]
    dependency_receipt_hashes: tuple[str, ...]
    dependency_dag_hash: str
    authority_class: AuthorityClass
    execution_context: str
    input_schema_hash: str
    output_schema_hash: str
    registry_hash: str
    provider_registry_hash: str
    resolved_at: str
    schema_version: int
    receipt_hash: str


@dataclass(frozen=True)
class CapabilityResolution:
    status: ResolutionStatus
    descriptor: CapabilityDescriptor | None
    receipt: CapabilityResolutionReceipt | None
    closure_receipts: tuple[CapabilityResolutionReceipt, ...] = ()
