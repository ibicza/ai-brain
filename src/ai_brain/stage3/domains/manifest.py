from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage3.capabilities.models import CapabilityRequirement


@dataclass(frozen=True)
class DomainPackManifest:
    domain_id: str
    pack_version: str
    schema_version: int
    canonical_name_ru: str
    canonical_name_en: str
    supported_languages: tuple[str, ...]
    subject_tags: tuple[str, ...]
    knowledge_record_hashes: tuple[str, ...]
    concept_graph_hash: str
    exercise_family_hashes: tuple[str, ...]
    source_binding_hashes: tuple[str, ...]
    required_capabilities: tuple[CapabilityRequirement, ...]
    adapter_binding_hashes: tuple[str, ...]
    evaluation_manifest_hash: str
    dependency_packs: tuple[str, ...]
    pack_content_hash: str
    created_at: str


@dataclass(frozen=True)
class AdapterBinding:
    adapter_id: str
    provider_implementation_hash: str
    capability_ids: tuple[str, ...]
    allowed_contexts: tuple[str, ...]
    compatible_pack_versions: tuple[str, ...]
    binding_hash: str


@dataclass(frozen=True)
class SourceBinding:
    binding_id: str
    fact_memory_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_hashes: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    source_chain_hash: str
    document_hashes: tuple[str, ...]
    segment_hashes: tuple[str, ...]
    field_evidence: tuple[tuple[str, str], ...]
    binding_hash: str


@dataclass(frozen=True)
class ExerciseFamilyBinding:
    family_id: str
    concept_ids: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    input_schema_hash: str
    answer_schema_hash: str
    difficulty_structure: tuple[str, ...]
    catalog_compiler_adapter: str
    grading_capability: str
    explanation_capability: str
    provenance_policy: str
    family_hash: str
