"""Immutable Stage-2 skill discovery, selection, and dispatch artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.models import ExecutionLimits
from ai_brain.stage2.version import STAGE2_SCHEMA_VERSION


class QuerySourceKind(StrEnum):
    STRUCTURED_SPEC = "STRUCTURED_SPEC"
    CONTROLLED_LANGUAGE = "CONTROLLED_LANGUAGE"
    ASSISTIVE_TEXT = "ASSISTIVE_TEXT"


class RetrievalMode(StrEnum):
    EXACT_SPECIFICATION = "EXACT_SPECIFICATION"
    EXACT_SEMANTIC = "EXACT_SEMANTIC"
    CONTROLLED_EXACT = "CONTROLLED_EXACT"
    LEXICAL = "LEXICAL"
    CHARACTER_NGRAM = "CHARACTER_NGRAM"
    BM25 = "BM25"
    LEARNED_BI_ENCODER = "LEARNED_BI_ENCODER"


class SearchStatus(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    AMBIGUOUS_VERSION = "AMBIGUOUS_VERSION"
    STALE_REGISTRY = "STALE_REGISTRY"
    INCOMPATIBLE_STAGE1 = "INCOMPATIBLE_STAGE1"
    CONTRADICTORY = "CONTRADICTORY"
    UNSUPPORTED = "UNSUPPORTED"
    CANDIDATES = "CANDIDATES"


class NextAction(StrEnum):
    SELECT_EXACT = "SELECT_EXACT"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    REVIEW_CANDIDATES = "REVIEW_CANDIDATES"
    RUN_SYNTHESIS = "RUN_SYNTHESIS"
    UNSUPPORTED = "UNSUPPORTED"


class ConfirmationDecision(StrEnum):
    PENDING = "PENDING"
    CONFIRM_SELECTION = "CONFIRM_SELECTION"
    REJECT_SELECTION = "REJECT_SELECTION"


@dataclass(frozen=True)
class SkillRecord:
    skill_id: str
    rule_id: str
    rule_semantic_hash: str
    specification_hash: str
    semantic_effect_hash: str
    installed_receipt_hash: str
    rule_version: int
    active: bool
    deprecated: bool
    canonical_name_ru: str
    canonical_name_en: str
    aliases_ru: tuple[str, ...]
    aliases_en: tuple[str, ...]
    controlled_examples_ru: tuple[str, ...]
    controlled_examples_en: tuple[str, ...]
    effect_summary: str
    input_state_schema: tuple[str, ...]
    effect_schema: dict[str, Any]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    supported_languages: tuple[str, ...]
    semantic_family: str
    provenance: dict[str, Any]
    created_at: str
    updated_at: str
    schema_version: int = STAGE2_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "aliases_ru",
            "aliases_en",
            "controlled_examples_ru",
            "controlled_examples_en",
            "input_state_schema",
            "preconditions",
            "postconditions",
            "supported_languages",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        # Registry JSON is the canonical representation.  Normalize nested tuples
        # here so a strict save/load roundtrip preserves dataclass equality.
        object.__setattr__(
            self,
            "effect_schema",
            json.loads(json.dumps(self.effect_schema, ensure_ascii=False)),
        )
        object.__setattr__(
            self,
            "provenance",
            json.loads(json.dumps(self.provenance, ensure_ascii=False)),
        )


@dataclass(frozen=True)
class SkillRegistryManifest:
    registry_version: int
    registry_hash: str
    rule_memory_hash: str
    stage1_version: str
    stage2_schema_version: int
    skill_count: int
    active_skill_count: int
    family_counts: dict[str, int]
    alias_count: int
    description_count: int
    semantic_effect_class_count: int
    order_sensitive_class_count: int
    order_insensitive_class_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SemanticEquivalenceGroup:
    semantic_effect_hash: str
    member_skill_ids: tuple[str, ...]
    canonical_skill_id: str
    equivalence_proof_kind: str
    order_sensitive: bool
    member_count: int

    def __post_init__(self) -> None:
        members = tuple(sorted(self.member_skill_ids))
        object.__setattr__(self, "member_skill_ids", members)
        if self.member_count != len(members):
            raise ValueError("semantic equivalence member count mismatch")
        if self.canonical_skill_id not in members:
            raise ValueError("canonical skill must be an equivalence member")


@dataclass(frozen=True)
class SkillQuery:
    query_id: str
    source_kind: QuerySourceKind
    original_input: str
    original_input_hash: str
    language: str | None
    specification: ProgramSpecification | None
    required_capabilities: tuple[str, ...]
    forbidden_effects: tuple[str, ...]
    state_schema: tuple[str, ...]
    created_at: str
    schema_version: int = STAGE2_SCHEMA_VERSION


@dataclass(frozen=True)
class SkillCandidate:
    skill_id: str
    rule_id: str
    rule_semantic_hash: str
    specification_hash: str
    score: float
    rank: int
    evidence: dict[str, Any]


@dataclass(frozen=True)
class SkillSearchResult:
    query_id: str
    query_hash: str
    registry_version: int
    registry_hash: str
    rule_memory_hash: str
    retrieval_mode: RetrievalMode
    status: SearchStatus
    candidates: tuple[SkillCandidate, ...]
    exact_match: bool
    ambiguous: bool
    novel: bool
    clarification_target: str | None
    clarification_question: str | None
    recommended_next_action: NextAction
    created_at: str
    result_hash: str
    schema_version: int = STAGE2_SCHEMA_VERSION


@dataclass(frozen=True)
class SkillSelectionReceipt:
    query_id: str
    query_hash: str
    registry_hash: str
    registry_version: int
    rule_memory_hash: str
    selected_skill_id: str
    rule_id: str
    rule_semantic_hash: str
    specification_hash: str
    retrieval_mode: RetrievalMode
    exact_match_evidence: dict[str, Any]
    candidate_list_hash: str
    confirmation_decision: ConfirmationDecision
    confirmer_identity: str
    confirmer_identity_type: str
    created_at: str
    stage1_version: str
    stage2_schema_version: int
    receipt_hash: str


@dataclass(frozen=True)
class SkillDispatchReceipt:
    selection_receipt_hash: str
    skill_id: str
    rule_id: str
    installed_receipt_hash: str
    rule_semantic_hash: str
    specification_hash: str
    initial_state_hash: str
    execution_limits: ExecutionLimits
    dispatch_policy: str
    stage1_execution_hash: str
    created_at: str
    dispatch_hash: str
    schema_version: int = STAGE2_SCHEMA_VERSION
