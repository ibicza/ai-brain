"""Independent structural and arithmetic verification of educational graphs."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from ai_brain.stage2.education.graph import verify_graph_hashes
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    EducationalGraphNode,
    GraphNodeKind,
)
from ai_brain.stage2.education.version import DERIVATION_GRAPH_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import content_hash

CALCULATION_KINDS = frozenset(
    {
        GraphNodeKind.MULTIPLY,
        GraphNodeKind.ADD,
        GraphNodeKind.DIVIDE,
        GraphNodeKind.UNIT_NORMALIZATION,
        GraphNodeKind.MOLE_RELATION,
        GraphNodeKind.AVOGADRO_RELATION,
        GraphNodeKind.ROUND_DISPLAY,
        GraphNodeKind.FINAL_RESULT,
    }
)
FACT_KINDS = frozenset({GraphNodeKind.FACT_LOOKUP, GraphNodeKind.ATOMIC_WEIGHT_LOOKUP})


def verify_derivation_graph(
    graph: EducationalDerivationGraph,
    *,
    expected_source_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verify_graph_hashes(graph)
    if graph.schema_version != DERIVATION_GRAPH_SCHEMA_VERSION:
        raise ValueError("incompatible educational graph schema")
    nodes = {node.node_id: node for node in graph.nodes}
    if len(nodes) != len(graph.nodes):
        raise ValueError("duplicate educational node ID")
    if graph.root_result_node_id not in nodes:
        raise ValueError("missing educational graph root")
    edge_keys = set()
    incoming: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in graph.edges:
        key = (edge.source_node_id, edge.target_node_id, edge.kind)
        if key in edge_keys:
            raise ValueError("duplicate educational graph edge")
        edge_keys.add(key)
        if edge.source_node_id not in nodes or edge.target_node_id not in nodes:
            raise ValueError("educational edge references a missing node")
        incoming[edge.target_node_id].add(edge.source_node_id)
    _reject_cycles(nodes, incoming)
    reachable = _dependencies_of(graph.root_result_node_id, incoming)
    meaningful = {
        node.node_id
        for node in graph.nodes
        if node.kind not in {GraphNodeKind.SOURCE_REFERENCE, GraphNodeKind.WARNING}
    }
    if not meaningful <= reachable | {graph.root_result_node_id}:
        raise ValueError("educational graph has disconnected calculation nodes")
    for node in graph.nodes:
        _verify_node(node, nodes)
        if node.kind in FACT_KINDS and (
            not node.claim_ids or not node.evidence_hashes or not node.source_hashes
        ):
            raise ValueError("factual educational node lacks provenance")
    root = nodes[graph.root_result_node_id]
    if root.kind != GraphNodeKind.FINAL_RESULT:
        raise ValueError("educational root must be FINAL_RESULT")
    if expected_source_result is not None:
        body = {
            key: value
            for key, value in expected_source_result.items()
            if key != "result_hash"
        }
        if (
            content_hash(body) != graph.source_result_hash
            or expected_source_result.get("result_hash") != graph.source_result_hash
        ):
            raise ValueError("educational graph source-result binding mismatch")
        expected = expected_source_result["result"]
        expected_value = (
            expected.get("element_counts")
            if expected_source_result["operation"] == "formula_composition"
            else expected.get("value", expected.get("canonical_formula"))
        )
        if expected_value is not None and str(root.exact_output) != str(expected_value):
            raise ValueError("educational graph root differs from source result")
    return {
        "status": "VERIFIED",
        "node_count": len(nodes),
        "edge_count": len(graph.edges),
        "recomputed_node_count": sum(
            node.kind in CALCULATION_KINDS for node in graph.nodes
        ),
        "graph_hash": graph.graph_hash,
    }


def _verify_node(
    node: EducationalGraphNode, nodes: dict[str, EducationalGraphNode]
) -> None:
    with localcontext() as context:
        context.prec = 120
        _verify_node_exact(node, nodes)


def _verify_node_exact(
    node: EducationalGraphNode, nodes: dict[str, EducationalGraphNode]
) -> None:
    if tuple(node.input_node_ids) != tuple(dict.fromkeys(node.input_node_ids)):
        raise ValueError("educational node has duplicate inputs")
    if any(node_id not in nodes for node_id in node.input_node_ids):
        raise ValueError("educational operation input is missing")
    if node.kind in CALCULATION_KINDS and not node.input_node_ids:
        raise ValueError("educational calculation node has no inputs")
    inputs = tuple(nodes[node_id].exact_output for node_id in node.input_node_ids)
    if node.kind == GraphNodeKind.MULTIPLY:
        expected = _decimal(inputs[0]) * _decimal(inputs[1])
        _compare_decimal(node.exact_output, expected)
    elif node.kind == GraphNodeKind.ADD:
        expected = sum((_decimal(value) for value in inputs), Decimal(0))
        _compare_decimal(node.exact_output, expected)
    elif node.kind == GraphNodeKind.DIVIDE:
        expected = _decimal(inputs[0]) / _decimal(inputs[1])
        _compare_decimal(node.exact_output, expected)
    elif node.kind == GraphNodeKind.UNIT_NORMALIZATION:
        factor = _decimal(node.metadata.get("factor"))
        _compare_decimal(node.exact_output, _decimal(inputs[0]) * factor)
    elif node.kind in {GraphNodeKind.MOLE_RELATION, GraphNodeKind.AVOGADRO_RELATION}:
        operation = node.operation
        if operation == "MULTIPLY":
            expected = _decimal(inputs[0]) * _decimal(inputs[1])
            if len(inputs) == 3:
                expected *= _decimal(inputs[2])
        elif operation == "DIVIDE":
            denominator = _decimal(inputs[1])
            if len(inputs) == 3:
                denominator *= _decimal(inputs[2])
            expected = _decimal(inputs[0]) / denominator
        else:
            raise ValueError("unsupported educational relation operation")
        _compare_decimal(node.exact_output, expected)
    elif node.kind == GraphNodeKind.ROUND_DISPLAY:
        _compare_decimal(node.exact_output, _decimal(inputs[0]))
        if not node.display_output:
            raise ValueError("rounding node lacks display output")
        _decimal(node.display_output)
    elif node.kind == GraphNodeKind.FINAL_RESULT:
        if isinstance(node.exact_output, (str, int, Decimal)) and isinstance(
            inputs[0], (str, int, Decimal)
        ):
            try:
                _compare_decimal(node.exact_output, _decimal(inputs[0]))
            except (TypeError, ValueError):
                if node.exact_output != inputs[0]:
                    raise ValueError(
                        "final educational result differs from its dependency"
                    ) from None
        elif node.exact_output != inputs[0]:
            raise ValueError("final educational result differs from its dependency")
        if node.unit != nodes[node.input_node_ids[0]].unit:
            raise ValueError("final educational result unit mismatch")


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise TypeError("educational arithmetic input is not a Decimal value")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("invalid educational Decimal value") from error
    if not result.is_finite():
        raise ValueError("non-finite educational Decimal value")
    return result


def _compare_decimal(actual: Any, expected: Decimal) -> None:
    with localcontext() as context:
        context.prec = 120
        if _decimal(actual) != expected:
            raise ValueError("educational calculation recomputation mismatch")


def _reject_cycles(
    nodes: dict[str, EducationalGraphNode], incoming: dict[str, set[str]]
) -> None:
    pending = {node_id: set(values) for node_id, values in incoming.items()}
    ready = [node_id for node_id, values in pending.items() if not values]
    seen = 0
    while ready:
        current = ready.pop()
        seen += 1
        for node_id, values in pending.items():
            if current in values:
                values.remove(current)
                if not values:
                    ready.append(node_id)
    if seen != len(nodes):
        raise ValueError("educational graph contains a cycle")


def _dependencies_of(root: str, incoming: dict[str, set[str]]) -> set[str]:
    result: set[str] = set()
    pending = list(incoming[root])
    while pending:
        current = pending.pop()
        if current not in result:
            result.add(current)
            pending.extend(incoming[current])
    return result
