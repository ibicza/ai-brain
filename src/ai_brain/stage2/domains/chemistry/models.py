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


class ChemistryReplayStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE_FACT_MEMORY = "STALE_FACT_MEMORY"
    STALE_ELEMENT_CLAIM = "STALE_ELEMENT_CLAIM"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    STALE_SOURCE = "STALE_SOURCE"
    STALE_DOMAIN_MANIFEST = "STALE_DOMAIN_MANIFEST"
    STALE_ATOMIC_WEIGHT_POLICY = "STALE_ATOMIC_WEIGHT_POLICY"
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
class AtomicWeightRecord:
    element_entity_id: str
    symbol: str
    standard_kind: AtomicWeightKind
    conventional_value: str
    standard_value: str | None
    interval_lower: str | None
    interval_upper: str | None
    unit: str
    claim_hashes: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_hashes: tuple[str, ...]
    policy_version: str
    record_hash: str


@dataclass(frozen=True)
class ChemistryKnowledgeSnapshot:
    domain_manifest_hash: str
    fact_memory_snapshot_hash: str
    atomic_weight_policy: str
    source_policy_version: str
    formula_grammar_version: str
    calculation_policy_version: str
    element_records: tuple[AtomicWeightRecord, ...]
    avogadro_constant: str
    avogadro_claim_hash: str
    avogadro_evidence_hashes: tuple[str, ...]
    avogadro_source_hashes: tuple[str, ...]
    claim_hashes: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_hashes: tuple[str, ...]
    snapshot_hash: str


@dataclass(frozen=True)
class ChemistryResultBundle:
    domain_version: str
    domain_manifest_hash: str
    operation: str
    formula: str | None
    formula_ast_hash: str | None
    composition_hash: str | None
    knowledge_snapshot_hash: str
    fact_memory_snapshot_hash: str
    claims_used: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_hashes: tuple[str, ...]
    calculation_steps: tuple[dict[str, Any], ...]
    result: dict[str, Any]
    warnings: tuple[str, ...]
    atomic_weight_policy: str
    formula_grammar_version: str
    calculation_policy_version: str
    rounding_policy: str
    result_hash: str
