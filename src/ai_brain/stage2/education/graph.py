"""Construction helpers for content-addressed educational graphs."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    EducationalGraphEdge,
    EducationalGraphNode,
    GraphEdgeKind,
    GraphNodeKind,
)
from ai_brain.stage2.education.version import DERIVATION_GRAPH_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import content_hash


def make_node(
    node_id: str,
    kind: GraphNodeKind,
    label: str,
    *,
    operation: str | None = None,
    input_node_ids: tuple[str, ...] = (),
    exact_inputs: tuple[str, ...] = (),
    exact_output: Any = None,
    unit: str | None = None,
    dimension: str | None = None,
    display_output: str | None = None,
    policy_version: str = "1.0",
    claim_ids: tuple[str, ...] = (),
    evidence_hashes: tuple[str, ...] = (),
    source_hashes: tuple[str, ...] = (),
    derivation_hashes: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> EducationalGraphNode:
    body = {
        "node_id": node_id,
        "kind": kind,
        "label": label,
        "operation": operation,
        "input_node_ids": input_node_ids,
        "exact_inputs": exact_inputs,
        "exact_output": exact_output,
        "unit": unit,
        "dimension": dimension,
        "display_output": display_output,
        "policy_version": policy_version,
        "claim_ids": claim_ids,
        "evidence_hashes": evidence_hashes,
        "source_hashes": source_hashes,
        "derivation_hashes": derivation_hashes,
        "metadata": metadata or {},
    }
    return EducationalGraphNode(**body, node_hash=content_hash(body))


def make_edge(
    source_node_id: str, target_node_id: str, kind: GraphEdgeKind
) -> EducationalGraphEdge:
    body = {
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "kind": kind,
    }
    return EducationalGraphEdge(**body, edge_hash=content_hash(body))


def make_graph(**values: Any) -> EducationalDerivationGraph:
    body = {**values, "schema_version": DERIVATION_GRAPH_SCHEMA_VERSION}
    digest = content_hash(body)
    return EducationalDerivationGraph(
        **body,
        graph_hash=digest,
    )


def verify_graph_hashes(graph: EducationalDerivationGraph) -> None:
    for node in graph.nodes:
        body = asdict(node)
        digest = body.pop("node_hash")
        if content_hash(body) != digest:
            raise ValueError(f"educational node hash mismatch: {node.node_id}")
    for edge in graph.edges:
        body = asdict(edge)
        digest = body.pop("edge_hash")
        if content_hash(body) != digest:
            raise ValueError("educational edge hash mismatch")
    body = asdict(graph)
    digest = body.pop("graph_hash")
    if content_hash(body) != digest:
        raise ValueError("educational graph hash mismatch")
