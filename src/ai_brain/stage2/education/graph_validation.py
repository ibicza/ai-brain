"""Independent v2 graph, typed-unit, interval, and rounding verification."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import render_significant
from ai_brain.stage2.domains.chemistry.models import ChemistryRoundingSpec
from ai_brain.stage2.education.graph import verify_graph_hashes
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    EducationalDimension,
    EducationalGraphNode,
    GraphNodeKind,
)
from ai_brain.stage2.education.version import DERIVATION_GRAPH_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.trusted_decimal import render_bounded_decimal

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
UNIT_DIMENSIONS = {
    "g": EducationalDimension.MASS,
    "kg": EducationalDimension.MASS,
    "mol": EducationalDimension.AMOUNT,
    "mmol": EducationalDimension.AMOUNT,
    "mol^-1": EducationalDimension.INVERSE_AMOUNT,
    "g/mol": EducationalDimension.MOLAR_MASS,
    "kg/mol": EducationalDimension.MOLAR_MASS,
    "u": EducationalDimension.ATOMIC_WEIGHT,
    "entities": EducationalDimension.ENTITY_COUNT,
}


def verify_derivation_graph(
    graph: EducationalDerivationGraph,
    *,
    expected_source_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verify_graph_hashes(graph)
    if graph.schema_version != DERIVATION_GRAPH_SCHEMA_VERSION:
        raise ValueError("incompatible educational graph schema")
    _verify_source_artifact(graph, expected_source_result)
    _verify_graph_provenance_binding(graph)
    nodes = {node.node_id: node for node in graph.nodes}
    if len(nodes) != len(graph.nodes) or graph.root_result_node_id not in nodes:
        raise ValueError("invalid educational graph node identity")
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
        if any(
            node_id not in incoming[node.node_id] for node_id in node.input_node_ids
        ):
            raise ValueError("educational node input lacks its graph edge")
        if node.kind in FACT_KINDS and (
            not node.claim_ids or not node.evidence_hashes or not node.source_hashes
        ):
            raise ValueError("factual educational node lacks provenance")
    root = nodes[graph.root_result_node_id]
    if root.kind != GraphNodeKind.FINAL_RESULT:
        raise ValueError("educational root must be FINAL_RESULT")
    _verify_root_against_source(graph, root)
    return {
        "status": "VERIFIED",
        "node_count": len(nodes),
        "edge_count": len(graph.edges),
        "recomputed_node_count": sum(
            node.kind in CALCULATION_KINDS for node in graph.nodes
        ),
        "graph_hash": graph.graph_hash,
    }


def canonical_exact(value: Any, dimension: EducationalDimension | None) -> str:
    """Return the one accepted typed representation for an input binding."""
    numeric = {
        EducationalDimension.MASS,
        EducationalDimension.AMOUNT,
        EducationalDimension.INVERSE_AMOUNT,
        EducationalDimension.MOLAR_MASS,
        EducationalDimension.ENTITY_COUNT,
        EducationalDimension.ATOMIC_WEIGHT,
        EducationalDimension.INTERVAL_MOLAR_MASS,
    }
    if dimension in numeric:
        if isinstance(value, dict):
            return canonical_json(
                {
                    "lower": render_bounded_decimal(_decimal(value["lower"])),
                    "upper": render_bounded_decimal(_decimal(value["upper"])),
                }
            )
        return render_bounded_decimal(_decimal(value))
    if dimension == EducationalDimension.COUNT:
        number = _decimal(value)
        if number != int(number):
            raise ValueError("count input is not an integer")
        return str(int(number))
    if dimension == EducationalDimension.COMPOSITION or isinstance(
        value, (dict, list, tuple)
    ):
        return canonical_json(value)
    if dimension == EducationalDimension.FORMULA and not isinstance(value, str):
        raise TypeError("formula value must be a string")
    return str(value)


def _verify_node(
    node: EducationalGraphNode, nodes: dict[str, EducationalGraphNode]
) -> None:
    with localcontext() as context:
        context.prec = 120
        if node.dimension is not None and not isinstance(
            node.dimension, EducationalDimension
        ):
            raise ValueError("unknown educational dimension")
        if tuple(node.input_node_ids) != tuple(dict.fromkeys(node.input_node_ids)):
            raise ValueError("educational node has duplicate inputs")
        if any(node_id not in nodes for node_id in node.input_node_ids):
            raise ValueError("educational operation input is missing")
        if len(node.input_node_ids) != len(node.exact_inputs):
            raise ValueError("educational exact input arity mismatch")
        inputs = tuple(nodes[node_id] for node_id in node.input_node_ids)
        for declared, source in zip(node.exact_inputs, inputs, strict=True):
            if declared != canonical_exact(source.exact_output, source.dimension):
                raise ValueError(
                    f"educational exact input is not bound to its input node: {node.node_id}"
                )
        if node.kind in CALCULATION_KINDS and not inputs:
            raise ValueError("educational calculation node has no inputs")
        if node.unit is not None:
            if node.unit not in UNIT_DIMENSIONS:
                raise ValueError("unknown educational unit")
            expected_dimension = UNIT_DIMENSIONS[node.unit]
            if node.dimension not in {
                expected_dimension,
                EducationalDimension.INTERVAL_MOLAR_MASS,
            }:
                raise ValueError("educational unit/dimension mismatch")
        try:
            _verify_operation(node, inputs)
        except (TypeError, ValueError) as error:
            raise type(error)(f"{error}: {node.node_id}") from error


def _verify_operation(
    node: EducationalGraphNode, inputs: tuple[EducationalGraphNode, ...]
) -> None:
    values = tuple(item.exact_output for item in inputs)
    if node.kind == GraphNodeKind.MULTIPLY:
        _require_arity(node, 2)
        if inputs[1].dimension != EducationalDimension.COUNT:
            raise ValueError("MULTIPLY requires a typed count multiplier")
        if node.dimension != inputs[0].dimension:
            raise ValueError("MULTIPLY output dimension mismatch")
        _compare_value(node.exact_output, _scale(values[0], values[1]))
    elif node.kind == GraphNodeKind.ADD:
        if not inputs or any(item.dimension != inputs[0].dimension for item in inputs):
            raise ValueError("ADD input dimensions differ")
        if node.dimension != inputs[0].dimension:
            raise ValueError("ADD output dimension mismatch")
        _compare_value(node.exact_output, _sum_values(values))
    elif node.kind == GraphNodeKind.DIVIDE:
        _require_arity(node, 2)
        denominator = _decimal(values[1])
        if denominator == 0:
            raise ValueError("DIVIDE denominator is zero")
        _compare_decimal(node.exact_output, _decimal(values[0]) / denominator)
    elif node.kind == GraphNodeKind.UNIT_NORMALIZATION:
        _require_arity(node, 1)
        if node.dimension != inputs[0].dimension:
            raise ValueError("unit conversion changes dimension")
        source_unit = node.metadata.get("source_unit")
        if source_unit != inputs[0].unit:
            raise ValueError("unit conversion source unit is unbound")
        factor = _decimal(node.metadata.get("factor"))
        if factor != _unit_factor(source_unit, node.unit):
            raise ValueError("unit conversion factor is incorrect")
        _compare_value(node.exact_output, _scale(values[0], factor))
    elif node.kind == GraphNodeKind.MOLE_RELATION:
        _require_arity(node, 2)
        left, right = inputs
        if (
            node.operation == "DIVIDE"
            and left.dimension == EducationalDimension.MASS
            and right.dimension == EducationalDimension.MOLAR_MASS
            and node.dimension == EducationalDimension.AMOUNT
        ):
            expected = _decimal(values[0]) / _decimal(values[1])
        elif (
            node.operation == "MULTIPLY"
            and left.dimension == EducationalDimension.AMOUNT
            and right.dimension == EducationalDimension.MOLAR_MASS
            and node.dimension == EducationalDimension.MASS
        ):
            expected = _decimal(values[0]) * _decimal(values[1])
        else:
            raise ValueError("invalid MOLE_RELATION dimension contract")
        _compare_decimal(node.exact_output, expected)
    elif node.kind == GraphNodeKind.AVOGADRO_RELATION:
        _require_arity(node, 3)
        left, constant, count = inputs
        if (
            constant.dimension != EducationalDimension.INVERSE_AMOUNT
            or count.dimension != EducationalDimension.COUNT
        ):
            raise ValueError("invalid Avogadro constant/count dimensions")
        if (
            node.operation == "MULTIPLY"
            and left.dimension == EducationalDimension.AMOUNT
            and node.dimension == EducationalDimension.ENTITY_COUNT
        ):
            expected = _decimal(values[0]) * _decimal(values[1]) * _decimal(values[2])
        elif (
            node.operation == "DIVIDE"
            and left.dimension == EducationalDimension.ENTITY_COUNT
            and node.dimension == EducationalDimension.AMOUNT
        ):
            expected = _decimal(values[0]) / (_decimal(values[1]) * _decimal(values[2]))
        else:
            raise ValueError("invalid AVOGADRO_RELATION dimension contract")
        _compare_decimal(node.exact_output, expected)
    elif node.kind == GraphNodeKind.ROUND_DISPLAY:
        _require_arity(node, 1)
        if node.dimension != inputs[0].dimension or node.unit != inputs[0].unit:
            raise ValueError("rounding changes typed value")
        _compare_value(node.exact_output, values[0])
        _verify_rounding(node)
    elif node.kind == GraphNodeKind.FINAL_RESULT:
        _require_arity(node, 1)
        _compare_value(node.exact_output, values[0])
        if node.unit != inputs[0].unit or node.dimension != inputs[0].dimension:
            raise ValueError("final educational result type mismatch")


def _verify_rounding(node: EducationalGraphNode) -> None:
    required = {
        "significant_digits",
        "rounding_mode",
        "trailing_zero_policy",
        "scientific_notation_policy",
        "rounding_spec_hash",
    }
    if not required <= set(node.metadata):
        raise ValueError("rounding node lacks its complete v2 specification")
    spec = ChemistryRoundingSpec(
        significant_digits=int(node.metadata["significant_digits"]),
        rounding_mode=str(node.metadata["rounding_mode"]),
    )
    if content_hash(spec) != node.metadata["rounding_spec_hash"]:
        raise ValueError("rounding specification hash mismatch")
    if isinstance(node.exact_output, dict):
        lower = _decimal(node.exact_output["lower"])
        upper = _decimal(node.exact_output["upper"])
        if lower > upper:
            raise ValueError("interval lower bound exceeds upper bound")
        expected = (
            f"[{render_significant(lower, spec)['rendered_value']}, "
            f"{render_significant(upper, spec)['rendered_value']}]"
        )
    else:
        expected = render_significant(_decimal(node.exact_output), spec)[
            "rendered_value"
        ]
    if node.display_output != expected:
        raise ValueError("rounded display does not match the declared policy")


def _verify_source_artifact(
    graph: EducationalDerivationGraph, expected: dict[str, Any] | None
) -> None:
    artifact = graph.source_result_artifact
    if not isinstance(artifact, dict) or not artifact:
        raise ValueError("graph lacks a complete source result artifact")
    if expected is not None and canonical_json(expected) != canonical_json(artifact):
        raise ValueError("graph source artifact differs from expected result")
    if graph.source_result_type.startswith("ChemistryResultBundle:"):
        body = {key: value for key, value in artifact.items() if key != "result_hash"}
        if artifact.get("result_hash") != content_hash(body):
            raise ValueError("invalid chemistry source result hash")
        if artifact["result_hash"] != graph.source_result_hash:
            raise ValueError("graph source result hash mismatch")
    elif graph.source_result_type == "ChemistryPairedFactAnswer":
        if set(artifact) != {
            "given",
            "answer",
            "given_result_hash",
            "answer_result_hash",
        }:
            raise ValueError("paired fact source result has an invalid schema")
        for role in ("given", "answer"):
            fact = artifact[role]
            if not isinstance(fact, dict):
                raise TypeError("paired fact source result is not an object")
            body = {key: value for key, value in fact.items() if key != "answer_hash"}
            if fact.get("answer_hash") != content_hash(body):
                raise ValueError("paired fact answer hash mismatch")
            if fact["answer_hash"] != artifact[f"{role}_result_hash"]:
                raise ValueError("paired fact result binding mismatch")
        digest = content_hash(
            {
                "given_result_hash": artifact.get("given_result_hash"),
                "answer_result_hash": artifact.get("answer_result_hash"),
            }
        )
        if digest != graph.source_result_hash:
            raise ValueError("paired fact source result hash mismatch")
    else:
        digest = artifact.get("answer_hash")
        if digest is None:
            digest = content_hash(artifact)
        else:
            digest = content_hash(
                {k: v for k, v in artifact.items() if k != "answer_hash"}
            )
        if digest != graph.source_result_hash:
            raise ValueError("fact source result hash mismatch")


def _verify_graph_provenance_binding(graph: EducationalDerivationGraph) -> None:
    artifact = graph.source_result_artifact
    if graph.source_result_type.startswith("ChemistryResultBundle:"):
        expected = {
            "claim_ids": tuple(artifact.get("claim_ids", ())),
            "evidence_hashes": tuple(artifact.get("evidence_hashes", ())),
            "source_hashes": tuple(artifact.get("source_hashes", ())),
            "derivation_hashes": tuple(artifact.get("derivation_hashes", ())),
        }
    elif graph.source_result_type == "ChemistryPairedFactAnswer":
        paired = (artifact.get("given", {}), artifact.get("answer", {}))
        expected = {
            "claim_ids": _paired_values(paired, "claim_ids"),
            "evidence_hashes": _paired_values(paired, "evidence_hashes"),
            "source_hashes": _paired_values(paired, "source_record_hashes"),
            "derivation_hashes": _paired_values(paired, "derivation_hashes"),
        }
    else:
        expected = {
            "claim_ids": tuple(artifact.get("claim_ids", ())),
            "evidence_hashes": tuple(artifact.get("evidence_hashes", ())),
            "source_hashes": tuple(artifact.get("source_record_hashes", ())),
            "derivation_hashes": tuple(artifact.get("derivation_hashes", ())),
        }
    for field, values in expected.items():
        if tuple(getattr(graph, field)) != values:
            raise ValueError(f"graph {field} is not bound to its source artifact")
    for node in graph.nodes:
        for field in expected:
            if not set(getattr(node, field)) <= set(expected[field]):
                raise ValueError(f"node {field} exceeds source-result provenance")


def _paired_values(
    artifacts: tuple[dict[str, Any], ...], field: str
) -> tuple[str, ...]:
    return tuple(
        sorted({value for artifact in artifacts for value in artifact.get(field, ())})
    )


def _verify_root_against_source(
    graph: EducationalDerivationGraph, root: EducationalGraphNode
) -> None:
    artifact = graph.source_result_artifact
    expected = None
    if graph.source_result_type.startswith("ChemistryResultBundle:"):
        result = artifact["result"]
        expected = result.get("element_counts", result.get("value"))
        if expected is None:
            expected = result.get(
                "exact_internal_value", result.get("canonical_formula")
            )
        if expected is None and "exact_internal_lower" in result:
            expected = {
                "lower": result["exact_internal_lower"],
                "upper": result["exact_internal_upper"],
            }
    elif graph.source_result_type == "ChemistryPairedFactAnswer":
        answer = artifact["answer"]
        expected = answer.get("value")
        if expected is None:
            if answer.get("value_requested") == "ABRIDGED":
                expected = answer["abridged_value"]
            elif answer.get("standard_kind") == "INTERVAL":
                expected = {
                    "lower": answer["standard_interval_lower"],
                    "upper": answer["standard_interval_upper"],
                }
            else:
                expected = answer.get("standard_nominal")
    if expected is not None:
        _compare_value(root.exact_output, expected)


def _scale(value: Any, factor: Any) -> Any:
    multiplier = _decimal(factor)
    if isinstance(value, dict):
        lower = _decimal(value["lower"]) * multiplier
        upper = _decimal(value["upper"]) * multiplier
        return {"lower": str(min(lower, upper)), "upper": str(max(lower, upper))}
    return _decimal(value) * multiplier


def _sum_values(values: tuple[Any, ...]) -> Any:
    if values and isinstance(values[0], dict):
        return {
            "lower": str(sum((_decimal(v["lower"]) for v in values), Decimal(0))),
            "upper": str(sum((_decimal(v["upper"]) for v in values), Decimal(0))),
        }
    return sum((_decimal(value) for value in values), Decimal(0))


def _compare_value(actual: Any, expected: Any) -> None:
    if isinstance(actual, dict) or isinstance(expected, dict):
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            raise TypeError("educational interval/scalar mismatch")
        if set(actual) != {"lower", "upper"} or set(expected) != {"lower", "upper"}:
            if canonical_json(actual) != canonical_json(expected):
                raise ValueError("educational structured result mismatch")
            return
        _compare_decimal(actual["lower"], _decimal(expected["lower"]))
        _compare_decimal(actual["upper"], _decimal(expected["upper"]))
        if _decimal(actual["lower"]) > _decimal(actual["upper"]):
            raise ValueError("invalid educational interval")
        return
    try:
        _compare_decimal(actual, _decimal(expected))
    except (InvalidOperation, TypeError, ValueError):
        if actual != expected:
            raise ValueError("educational result mismatch") from None


def _require_arity(node: EducationalGraphNode, arity: int) -> None:
    if len(node.input_node_ids) != arity:
        raise ValueError(f"{node.kind.value} requires arity {arity}")


def _unit_factor(source: str | None, target: str | None) -> Decimal:
    factors = {
        ("g", "kg"): Decimal("0.001"),
        ("kg", "g"): Decimal(1000),
        ("mol", "mmol"): Decimal(1000),
        ("mmol", "mol"): Decimal("0.001"),
        ("g/mol", "kg/mol"): Decimal("0.001"),
        ("kg/mol", "g/mol"): Decimal(1000),
    }
    try:
        return factors[(source, target)]
    except KeyError as error:
        raise ValueError("unsupported exact educational unit conversion") from error


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
