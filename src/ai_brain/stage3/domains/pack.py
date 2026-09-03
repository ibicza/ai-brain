from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage3.domains.aliases import AliasSemantics
from ai_brain.stage3.domains.manifest import (
    AdapterBinding,
    DomainPackManifest,
    ExerciseFamilyBinding,
    SourceBinding,
)
from ai_brain.stage3.knowledge_ir.records import KnowledgeRecord


class ConceptEdgeKind(StrEnum):
    PREREQUISITE = "PREREQUISITE"
    IS_A = "IS_A"
    PART_OF = "PART_OF"
    DEPENDS_ON = "DEPENDS_ON"
    CONTRASTS_WITH = "CONTRASTS_WITH"
    ENABLES = "ENABLES"
    RELATED_TO = "RELATED_TO"


@dataclass(frozen=True)
class ConceptNode:
    concept_id: str
    knowledge_id: str
    canonical_name_ru: str
    canonical_name_en: str
    node_hash: str


@dataclass(frozen=True)
class ConceptEdge:
    source_concept_id: str
    target_concept_id: str
    kind: ConceptEdgeKind
    dependency_pack: str | None
    edge_hash: str


@dataclass(frozen=True)
class ConceptGraph:
    nodes: tuple[ConceptNode, ...]
    edges: tuple[ConceptEdge, ...]
    schema_version: int
    graph_hash: str


@dataclass(frozen=True)
class DomainPack:
    root: str
    manifest: DomainPackManifest
    knowledge_records: tuple[KnowledgeRecord, ...]
    concept_graph: ConceptGraph
    exercise_families: tuple[ExerciseFamilyBinding, ...]
    adapter_bindings: tuple[AdapterBinding, ...]
    source_bindings: tuple[SourceBinding, ...]
    evaluation_manifest: dict
    alias_semantics: AliasSemantics | None = None
