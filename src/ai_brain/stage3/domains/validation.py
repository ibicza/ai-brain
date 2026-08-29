from __future__ import annotations

import re
from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash, normalize_datetime
from ai_brain.stage3.domains.pack import ConceptEdgeKind, ConceptGraph, DomainPack
from ai_brain.stage3.knowledge_ir.validation import validate_records
from ai_brain.stage3.knowledge_ir.version import (
    CONCEPT_GRAPH_SCHEMA_VERSION,
    DOMAIN_PACK_SCHEMA_VERSION,
)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_unique(values, label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {label}")


def _require_hashes(values, label: str) -> None:
    if any(not _SHA256.fullmatch(value) for value in values):
        raise ValueError(f"invalid {label} SHA-256")


def hash_without(value, field: str) -> str:
    body = asdict(value)
    body.pop(field)
    return content_hash(body)


def validate_concept_graph(
    graph: ConceptGraph, dependency_packs: tuple[str, ...] = ()
) -> None:
    if graph.schema_version != CONCEPT_GRAPH_SCHEMA_VERSION:
        raise ValueError("unsupported concept graph schema")
    ids = {x.concept_id for x in graph.nodes}
    if len(ids) != len(graph.nodes):
        raise ValueError("duplicate concept ID")
    for node in graph.nodes:
        if node.node_hash != hash_without(node, "node_hash"):
            raise ValueError("concept node hash mismatch")
    for edge in graph.edges:
        if edge.edge_hash != hash_without(edge, "edge_hash"):
            raise ValueError("concept edge hash mismatch")
        if edge.source_concept_id not in ids:
            raise ValueError("dangling concept edge source")
        if (
            edge.target_concept_id not in ids
            and edge.dependency_pack not in dependency_packs
        ):
            raise ValueError("cross-pack edge lacks declared dependency")
    prereq = {x: [] for x in ids}
    for edge in graph.edges:
        if edge.kind is ConceptEdgeKind.PREREQUISITE and edge.target_concept_id in ids:
            prereq[edge.source_concept_id].append(edge.target_concept_id)
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("concept prerequisite cycle")
        if node in done:
            return
        visiting.add(node)
        for child in prereq[node]:
            visit(child)
        visiting.remove(node)
        done.add(node)

    for node in ids:
        visit(node)
    if graph.graph_hash != hash_without(graph, "graph_hash"):
        raise ValueError("concept graph hash mismatch")


def validate_pack(pack: DomainPack) -> dict[str, object]:
    manifest = pack.manifest
    if manifest.schema_version != DOMAIN_PACK_SCHEMA_VERSION:
        raise ValueError("unsupported domain pack schema")
    if (
        not manifest.domain_id
        or not manifest.canonical_name_en
        or not manifest.canonical_name_ru
    ):
        raise ValueError("domain pack identity and RU/EN names are required")
    if not _IDENTIFIER.fullmatch(manifest.domain_id) or ".." in manifest.domain_id:
        raise ValueError("unsafe domain identity")
    if not set(manifest.supported_languages) <= {"ru", "en"}:
        raise ValueError("unsupported pack language")
    normalize_datetime(manifest.created_at)
    validate_records(pack.knowledge_records)
    validate_concept_graph(pack.concept_graph, manifest.dependency_packs)
    if any(item.domain_id != manifest.domain_id for item in pack.knowledge_records):
        raise ValueError("knowledge record belongs to another domain")
    knowledge_ids = {item.knowledge_id for item in pack.knowledge_records}
    if any(item.knowledge_id not in knowledge_ids for item in pack.concept_graph.nodes):
        raise ValueError("concept node has a dangling knowledge reference")
    _require_unique(manifest.dependency_packs, "pack dependency")
    if manifest.domain_id in manifest.dependency_packs:
        raise ValueError("domain pack cannot depend on itself")
    if manifest.knowledge_record_hashes != tuple(
        x.content_hash for x in pack.knowledge_records
    ):
        raise ValueError("knowledge record manifest mismatch")
    if manifest.concept_graph_hash != pack.concept_graph.graph_hash:
        raise ValueError("concept graph manifest mismatch")
    concepts = {x.concept_id for x in pack.concept_graph.nodes}
    declared_capabilities = {
        item.capability_id for item in manifest.required_capabilities
    }
    _require_unique(
        tuple(item.capability_id for item in manifest.required_capabilities),
        "capability requirement",
    )
    for record in pack.knowledge_records:
        if not set(record.required_capability_ids) <= declared_capabilities:
            raise ValueError("knowledge record uses an undeclared capability")
    families: set[str] = set()
    for item in pack.exercise_families:
        if item.family_id in families or not set(item.concept_ids) <= concepts:
            raise ValueError("exercise family has duplicate or unknown concepts")
        families.add(item.family_id)
        if not set(item.required_capabilities) <= declared_capabilities:
            raise ValueError("exercise family uses an undeclared capability")
        if item.family_hash != hash_without(item, "family_hash"):
            raise ValueError("exercise family hash mismatch")
    if manifest.exercise_family_hashes != tuple(
        x.family_hash for x in pack.exercise_families
    ):
        raise ValueError("exercise family manifest mismatch")
    adapter_ids = tuple(item.adapter_id for item in pack.adapter_bindings)
    _require_unique(adapter_ids, "adapter ID")
    for item in pack.adapter_bindings:
        if not _IDENTIFIER.fullmatch(item.adapter_id) or ".." in item.adapter_id:
            raise ValueError("unsafe adapter identity")
        if not set(item.capability_ids) <= declared_capabilities:
            raise ValueError("adapter supplies an undeclared capability")
        if manifest.pack_version not in item.compatible_pack_versions:
            raise ValueError("adapter is incompatible with the pack version")
        _require_hashes((item.provider_implementation_hash,), "adapter provider")
        if item.binding_hash != hash_without(item, "binding_hash"):
            raise ValueError("adapter binding hash mismatch")
    source_ids = tuple(item.binding_id for item in pack.source_bindings)
    _require_unique(source_ids, "source binding ID")
    for item in pack.source_bindings:
        if not _IDENTIFIER.fullmatch(item.binding_id) or ".." in item.binding_id:
            raise ValueError("unsafe source binding identity")
        _require_hashes(
            (
                *item.fact_memory_refs,
                *item.claim_refs,
                *item.evidence_hashes,
                *item.source_hashes,
                *item.derivation_hashes,
                *item.document_hashes,
                *item.segment_hashes,
                *(digest for _, digest in item.field_evidence),
                item.source_chain_hash,
            ),
            "source reference",
        )
        if item.binding_hash != hash_without(item, "binding_hash"):
            raise ValueError("source binding hash mismatch")
    source_id_set = set(source_ids)
    if any(
        not set(record.provenance_refs) <= source_id_set
        for record in pack.knowledge_records
    ):
        raise ValueError("knowledge record has a dangling provenance reference")
    if manifest.adapter_binding_hashes != tuple(
        x.binding_hash for x in pack.adapter_bindings
    ):
        raise ValueError("adapter binding manifest mismatch")
    if manifest.source_binding_hashes != tuple(
        x.binding_hash for x in pack.source_bindings
    ):
        raise ValueError("source binding manifest mismatch")
    if manifest.evaluation_manifest_hash != content_hash(pack.evaluation_manifest):
        raise ValueError("evaluation manifest hash mismatch")
    if set(pack.evaluation_manifest) != {
        "schema_version",
        "test_cases",
        "minimum_pass_rate",
        "runtime_network",
        "expected_record_count",
        "source_span_exactness",
    }:
        raise ValueError("evaluation manifest has unsupported fields")
    if (
        pack.evaluation_manifest["schema_version"] != 2
        or pack.evaluation_manifest["runtime_network"] is not False
        or not pack.evaluation_manifest["test_cases"]
        or pack.evaluation_manifest["expected_record_count"]
        != len(pack.knowledge_records)
        or pack.evaluation_manifest["source_span_exactness"] != "1.0"
    ):
        raise ValueError("evaluation manifest violates the offline test policy")
    body = asdict(manifest)
    body.pop("pack_content_hash")
    if manifest.pack_content_hash != content_hash(body):
        raise ValueError("domain pack content hash mismatch")
    return {
        "status": "VERIFIED",
        "domain_id": manifest.domain_id,
        "pack_version": manifest.pack_version,
        "pack_hash": manifest.pack_content_hash,
        "knowledge_record_count": len(pack.knowledge_records),
        "concept_count": len(pack.concept_graph.nodes),
        "exercise_family_count": len(pack.exercise_families),
    }
