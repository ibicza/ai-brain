"""Exact graph builders over immutable chemistry result bundles."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from ai_brain.stage2.education.graph import make_edge, make_graph, make_node
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import GraphEdgeKind, GraphNodeKind
from ai_brain.stage2.education.version import DERIVATION_GRAPH_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import content_hash, utc_now


def build_result_graph(
    result: dict[str, Any],
    *,
    tool_implementation_hash: str,
    request_hash: str | None = None,
    route_decision_hash: str | None = None,
    created_at: str | None = None,
) -> Any:
    _verify_result_hash(result)
    operation = result["operation"]
    builders = {
        "formula_composition": _formula_graph,
        "molar_mass": _molar_mass_graph,
        "mass_amount": _mass_amount_graph,
        "entity_amount": _entity_amount_graph,
    }
    if operation not in builders:
        raise ValueError(f"unsupported educational source result: {operation}")
    nodes, edges, root = builders[operation](result)
    source_nodes, source_edges = _source_nodes(result, nodes)
    warning_nodes, warning_edges = _warning_nodes(result, root)
    graph = make_graph(
        graph_id=f"education.graph.{result['result_hash'][:24]}",
        domain_id="chemistry",
        domain_version=result["domain_version"],
        source_result_type=f"ChemistryResultBundle:{operation}",
        source_result_hash=result["result_hash"],
        request_hash=request_hash
        or content_hash(
            {
                "operation": operation,
                "formula": result.get("formula"),
                "steps": result.get("calculation_steps", ()),
            }
        ),
        route_decision_hash=route_decision_hash,
        fact_memory_snapshot_hash=result["fact_memory_snapshot_hash"],
        knowledge_snapshot_hash=result["knowledge_snapshot_hash"],
        formula_ast_hash=result.get("formula_ast_hash"),
        tool_implementation_hash=tool_implementation_hash,
        calculation_policy_version=result["calculation_policy_version"],
        rounding_policy_hash=result["rounding_policy_hash"],
        source_chain_version=result["source_chain_version"],
        source_chain_hash=result["source_chain_hash"],
        nodes=(*nodes, *source_nodes, *warning_nodes),
        edges=(*edges, *source_edges, *warning_edges),
        root_result_node_id=root,
        claim_ids=tuple(result["claim_ids"]),
        evidence_hashes=tuple(result["evidence_hashes"]),
        source_hashes=tuple(result["source_hashes"]),
        derivation_hashes=tuple(result["derivation_hashes"]),
        created_at=created_at or utc_now(),
    )
    if graph.schema_version != DERIVATION_GRAPH_SCHEMA_VERSION:
        raise AssertionError("graph constructor returned an incompatible schema")
    verify_derivation_graph(graph, expected_source_result=result)
    return graph


def build_fact_graph(
    answer: dict[str, Any],
    *,
    domain_version: str,
    domain_manifest_hash: str,
    source_chain_version: str,
    source_chain_hash: str,
    field_name: str,
    value: Any,
    unit: str | None,
    request_hash: str,
    created_at: str | None = None,
) -> Any:
    answer_hash = answer.get("answer_hash")
    if not isinstance(answer_hash, str):
        answer_hash = content_hash(answer)
    fact = make_node(
        "n1",
        GraphNodeKind.FACT_LOOKUP,
        field_name,
        exact_output=value,
        unit=unit,
        dimension=_dimension(unit),
        claim_ids=tuple(
            answer.get("claim_ids", (answer.get("element_entity_id", ""),))
        ),
        evidence_hashes=tuple(answer.get("evidence_hashes", ())),
        source_hashes=tuple(answer.get("source_record_hashes", ())),
        derivation_hashes=tuple(answer.get("derivation_hashes", ())),
        metadata={
            "field_name": field_name,
            "domain_manifest_hash": domain_manifest_hash,
        },
    )
    final = make_node(
        "n2",
        GraphNodeKind.FINAL_RESULT,
        "fact result",
        operation="IDENTITY",
        input_node_ids=(fact.node_id,),
        exact_inputs=(str(value),),
        exact_output=value,
        unit=unit,
        dimension=_dimension(unit),
        display_output=str(value),
    )
    source_nodes = tuple(
        make_node(
            f"s{index}",
            GraphNodeKind.SOURCE_REFERENCE,
            "verified source",
            exact_output=source_hash,
            source_hashes=(source_hash,),
            metadata={"source_hash": source_hash},
        )
        for index, source_hash in enumerate(fact.source_hashes, start=1)
    )
    graph = make_graph(
        graph_id=f"education.graph.{answer_hash[:24]}",
        domain_id="chemistry",
        domain_version=domain_version,
        source_result_type="ChemistryFactAnswer",
        source_result_hash=answer_hash,
        request_hash=request_hash,
        route_decision_hash=None,
        fact_memory_snapshot_hash=answer["fact_memory_snapshot_hash"],
        knowledge_snapshot_hash=answer_hash,
        formula_ast_hash=None,
        tool_implementation_hash=None,
        calculation_policy_version="FACT_LOOKUP",
        rounding_policy_hash=content_hash("NO_ROUNDING"),
        source_chain_version=source_chain_version,
        source_chain_hash=source_chain_hash,
        nodes=(fact, final, *source_nodes),
        edges=(
            make_edge("n1", "n2", GraphEdgeKind.SUPPORTS_RESULT),
            *(
                make_edge(node.node_id, "n1", GraphEdgeKind.CITES_SOURCE)
                for node in source_nodes
            ),
        ),
        root_result_node_id="n2",
        claim_ids=fact.claim_ids,
        evidence_hashes=fact.evidence_hashes,
        source_hashes=fact.source_hashes,
        derivation_hashes=fact.derivation_hashes,
        created_at=created_at or utc_now(),
    )
    verify_derivation_graph(graph)
    return graph


def _formula_graph(result: dict[str, Any]):
    formula = result["formula"]
    composition = result["result"]["element_counts"]
    given = make_node(
        "n1",
        GraphNodeKind.GIVEN_VALUE,
        "chemical formula",
        exact_output=formula,
        metadata={"value_type": "formula"},
    )
    parsed = make_node(
        "n2",
        GraphNodeKind.FORMULA_PARSE,
        "parsed formula",
        operation="PARSE",
        input_node_ids=("n1",),
        exact_inputs=(formula,),
        exact_output=formula,
        metadata={
            "formula_ast_hash": result["formula_ast_hash"],
            "composition": composition,
            "grammar_version": result["formula_grammar_version"],
        },
    )
    composed = make_node(
        "n3",
        GraphNodeKind.FORMULA_COMPOSITION,
        "element counts",
        operation="COMPOSE",
        input_node_ids=("n2",),
        exact_inputs=(formula,),
        exact_output=composition,
        metadata={"total_atom_count": result["result"]["total_atom_count"]},
    )
    final = make_node(
        "n4",
        GraphNodeKind.FINAL_RESULT,
        "formula composition result",
        operation="IDENTITY",
        input_node_ids=("n3",),
        exact_output=composition,
        display_output=", ".join(f"{k}:{v}" for k, v in composition.items()),
    )
    return (
        (given, parsed, composed, final),
        (
            make_edge("n1", "n2", GraphEdgeKind.DEPENDS_ON),
            make_edge("n2", "n3", GraphEdgeKind.USES_FORMULA_TERM),
            make_edge("n3", "n4", GraphEdgeKind.SUPPORTS_RESULT),
        ),
        "n4",
    )


def _molar_mass_graph(result: dict[str, Any]):
    nodes = [
        make_node(
            "n1",
            GraphNodeKind.GIVEN_VALUE,
            "chemical formula",
            exact_output=result["formula"],
            metadata={"value_type": "formula"},
        ),
        make_node(
            "n2",
            GraphNodeKind.FORMULA_PARSE,
            "parsed formula",
            operation="PARSE",
            input_node_ids=("n1",),
            exact_inputs=(result["formula"],),
            exact_output=result["formula"],
            metadata={
                "formula_ast_hash": result["formula_ast_hash"],
                "composition": {
                    row["symbol"]: row["count"] for row in result["calculation_steps"]
                },
                "grammar_version": result["formula_grammar_version"],
            },
        ),
    ]
    edges = [make_edge("n1", "n2", GraphEdgeKind.DEPENDS_ON)]
    contribution_ids = []
    for index, step in enumerate(result["calculation_steps"], start=1):
        base = 3 + (index - 1) * 3
        weight = step.get("abridged_atomic_weight", step.get("exact_lower"))
        contribution = step.get("exact_contribution_g_per_mol")
        if contribution is None:
            contribution = str(Decimal(weight) * int(step["count"]))
        fact_id, count_id, multiply_id = f"n{base}", f"n{base + 1}", f"n{base + 2}"
        nodes.extend(
            (
                make_node(
                    fact_id,
                    GraphNodeKind.ATOMIC_WEIGHT_LOOKUP,
                    f"atomic weight {step['symbol']}",
                    exact_output=weight,
                    unit="g/mol",
                    dimension="MOLAR_MASS",
                    claim_ids=tuple(result["claim_ids"]),
                    evidence_hashes=tuple(result["evidence_hashes"]),
                    source_hashes=tuple(result["source_hashes"]),
                    derivation_hashes=tuple(result["derivation_hashes"]),
                    metadata={"symbol": step["symbol"]},
                ),
                make_node(
                    count_id,
                    GraphNodeKind.STOICHIOMETRIC_COUNT,
                    f"count {step['symbol']}",
                    input_node_ids=("n2",),
                    exact_output=step["count"],
                    dimension="COUNT",
                    metadata={"symbol": step["symbol"]},
                ),
                make_node(
                    multiply_id,
                    GraphNodeKind.MULTIPLY,
                    f"contribution {step['symbol']}",
                    operation="MULTIPLY",
                    input_node_ids=(fact_id, count_id),
                    exact_inputs=(str(weight), str(step["count"])),
                    exact_output=contribution,
                    unit="g/mol",
                    dimension="MOLAR_MASS",
                    metadata={"symbol": step["symbol"]},
                ),
            )
        )
        edges.extend(
            (
                make_edge("n2", count_id, GraphEdgeKind.USES_FORMULA_TERM),
                make_edge(fact_id, multiply_id, GraphEdgeKind.USES_FACT),
                make_edge(count_id, multiply_id, GraphEdgeKind.CONTRIBUTES_TO),
            )
        )
        contribution_ids.append(multiply_id)
    next_id = 3 + len(result["calculation_steps"]) * 3
    raw_total = result["result"]["exact_internal_value"]
    unit = result["result"]["unit"]
    total_before_unit = raw_total
    if unit == "kg/mol":
        total_before_unit = str(Decimal(raw_total) * Decimal(1000))
    total_id = f"n{next_id}"
    nodes.append(
        make_node(
            total_id,
            GraphNodeKind.ADD,
            "sum contributions",
            operation="ADD",
            input_node_ids=tuple(contribution_ids),
            exact_inputs=tuple(
                str(next(node.exact_output for node in nodes if node.node_id == item))
                for item in contribution_ids
            ),
            exact_output=total_before_unit,
            unit="g/mol",
            dimension="MOLAR_MASS",
        )
    )
    edges.extend(
        make_edge(item, total_id, GraphEdgeKind.CONTRIBUTES_TO)
        for item in contribution_ids
    )
    current_id = total_id
    if unit == "kg/mol":
        next_id += 1
        normalized_id = f"n{next_id}"
        nodes.append(
            make_node(
                normalized_id,
                GraphNodeKind.UNIT_NORMALIZATION,
                "g/mol to kg/mol",
                operation="MULTIPLY",
                input_node_ids=(current_id,),
                exact_inputs=(total_before_unit,),
                exact_output=raw_total,
                unit=unit,
                dimension="MOLAR_MASS",
                metadata={"factor": "0.001", "source_unit": "g/mol"},
            )
        )
        edges.append(
            make_edge(current_id, normalized_id, GraphEdgeKind.NORMALIZES_UNIT)
        )
        current_id = normalized_id
    next_id += 1
    round_id = f"n{next_id}"
    nodes.append(
        make_node(
            round_id,
            GraphNodeKind.ROUND_DISPLAY,
            "display rounding",
            operation="ROUND_DISPLAY",
            input_node_ids=(current_id,),
            exact_inputs=(raw_total,),
            exact_output=raw_total,
            unit=unit,
            dimension="MOLAR_MASS",
            display_output=result["result"]["rendered_value"],
            policy_version=result["rounding_policy"],
            metadata={"significant_digits": result["result"]["significant_digits"]},
        )
    )
    edges.append(make_edge(current_id, round_id, GraphEdgeKind.ROUNDS_FOR_DISPLAY))
    next_id += 1
    final_id = f"n{next_id}"
    nodes.append(
        make_node(
            final_id,
            GraphNodeKind.FINAL_RESULT,
            "molar mass",
            operation="IDENTITY",
            input_node_ids=(round_id,),
            exact_inputs=(raw_total,),
            exact_output=raw_total,
            unit=unit,
            dimension="MOLAR_MASS",
            display_output=result["result"]["rendered_value"],
        )
    )
    edges.append(make_edge(round_id, final_id, GraphEdgeKind.SUPPORTS_RESULT))
    return tuple(nodes), tuple(edges), final_id


def _mass_amount_graph(result: dict[str, Any]):
    step_input, step_mm = result["calculation_steps"]
    source_unit = step_input["source_unit"]
    target_unit = result["result"]["unit"]
    value = step_input["exact_input"]
    mm = step_mm["exact_molar_mass"]
    nodes = [
        make_node(
            "n1",
            GraphNodeKind.GIVEN_VALUE,
            "input quantity",
            exact_output=value,
            unit=source_unit,
            dimension=_dimension(source_unit),
        ),
        make_node(
            "n2",
            GraphNodeKind.FACT_LOOKUP,
            "molar mass",
            exact_output=mm,
            unit="g/mol",
            dimension="MOLAR_MASS",
            claim_ids=tuple(result["claim_ids"]),
            evidence_hashes=tuple(result["evidence_hashes"]),
            source_hashes=tuple(result["source_hashes"]),
            derivation_hashes=tuple(result["derivation_hashes"]),
        ),
    ]
    edges = []
    base_value, base_unit, input_factor = _to_base(value, source_unit)
    current = "n1"
    if input_factor != "1":
        nodes.append(
            make_node(
                "n3",
                GraphNodeKind.UNIT_NORMALIZATION,
                "normalize input unit",
                operation="MULTIPLY",
                input_node_ids=("n1",),
                exact_inputs=(value,),
                exact_output=base_value,
                unit=base_unit,
                dimension=_dimension(base_unit),
                metadata={"factor": input_factor, "source_unit": source_unit},
            )
        )
        edges.append(make_edge("n1", "n3", GraphEdgeKind.NORMALIZES_UNIT))
        current = "n3"
        relation_id = "n4"
    else:
        relation_id = "n3"
    mass_to_amount = base_unit == "g"
    with localcontext() as context:
        context.prec = 120
        relation_value = (
            Decimal(base_value) / Decimal(mm)
            if mass_to_amount
            else Decimal(base_value) * Decimal(mm)
        )
    nodes.append(
        make_node(
            relation_id,
            GraphNodeKind.MOLE_RELATION,
            "mass amount relation",
            operation="DIVIDE" if mass_to_amount else "MULTIPLY",
            input_node_ids=(current, "n2"),
            exact_inputs=(base_value, mm),
            exact_output=str(relation_value),
            unit="mol" if mass_to_amount else "g",
            dimension="AMOUNT" if mass_to_amount else "MASS",
        )
    )
    edges.extend(
        (
            make_edge(current, relation_id, GraphEdgeKind.DEPENDS_ON),
            make_edge("n2", relation_id, GraphEdgeKind.USES_FACT),
        )
    )
    current = relation_id
    output_factor = _from_base_factor(target_unit)
    next_number = int(relation_id[1:]) + 1
    if output_factor != "1":
        normalized_id = f"n{next_number}"
        exact = Decimal(str(relation_value)) * Decimal(output_factor)
        nodes.append(
            make_node(
                normalized_id,
                GraphNodeKind.UNIT_NORMALIZATION,
                "normalize output unit",
                operation="MULTIPLY",
                input_node_ids=(current,),
                exact_inputs=(str(relation_value),),
                exact_output=str(exact),
                unit=target_unit,
                dimension=_dimension(target_unit),
                metadata={"factor": output_factor, "source_unit": nodes[-1].unit},
            )
        )
        edges.append(make_edge(current, normalized_id, GraphEdgeKind.NORMALIZES_UNIT))
        current = normalized_id
        next_number += 1
    round_id = f"n{next_number}"
    exact_result = result["result"]["exact_internal_value"]
    nodes.append(
        make_node(
            round_id,
            GraphNodeKind.ROUND_DISPLAY,
            "display rounding",
            operation="ROUND_DISPLAY",
            input_node_ids=(current,),
            exact_inputs=(exact_result,),
            exact_output=exact_result,
            unit=target_unit,
            dimension=_dimension(target_unit),
            display_output=result["result"]["rendered_value"],
            policy_version=result["rounding_policy"],
        )
    )
    edges.append(make_edge(current, round_id, GraphEdgeKind.ROUNDS_FOR_DISPLAY))
    final_id = f"n{next_number + 1}"
    nodes.append(
        make_node(
            final_id,
            GraphNodeKind.FINAL_RESULT,
            "converted quantity",
            operation="IDENTITY",
            input_node_ids=(round_id,),
            exact_output=exact_result,
            unit=target_unit,
            dimension=_dimension(target_unit),
            display_output=result["result"]["rendered_value"],
        )
    )
    edges.append(make_edge(round_id, final_id, GraphEdgeKind.SUPPORTS_RESULT))
    return tuple(nodes), tuple(edges), final_id


def _entity_amount_graph(result: dict[str, Any]):
    step = result["calculation_steps"][0]
    value = step["exact_input"]
    source_unit = step["source_unit"]
    target_unit = step["target_unit"]
    constant = step["avogadro_constant"]
    multiplier = str(step["stoichiometric_multiplier"])
    nodes = [
        make_node(
            "n1",
            GraphNodeKind.GIVEN_VALUE,
            "input quantity",
            exact_output=value,
            unit=source_unit,
            dimension=_dimension(source_unit),
        ),
        make_node(
            "n2",
            GraphNodeKind.FACT_LOOKUP,
            "Avogadro constant",
            exact_output=constant,
            unit="mol^-1",
            dimension="INVERSE_AMOUNT",
            claim_ids=tuple(result["claim_ids"]),
            evidence_hashes=tuple(result["evidence_hashes"]),
            source_hashes=tuple(result["source_hashes"]),
            derivation_hashes=tuple(result["derivation_hashes"]),
        ),
        make_node(
            "n3",
            GraphNodeKind.STOICHIOMETRIC_COUNT,
            "entity multiplier",
            exact_output=multiplier,
            dimension="COUNT",
            metadata={"basis": step["basis"]},
        ),
    ]
    edges = []
    current = "n1"
    base_value, base_unit, factor = _to_base(value, source_unit)
    next_number = 4
    if factor != "1":
        nodes.append(
            make_node(
                "n4",
                GraphNodeKind.UNIT_NORMALIZATION,
                "normalize amount",
                operation="MULTIPLY",
                input_node_ids=("n1",),
                exact_inputs=(value,),
                exact_output=base_value,
                unit=base_unit,
                dimension=_dimension(base_unit),
                metadata={"factor": factor, "source_unit": source_unit},
            )
        )
        edges.append(make_edge("n1", "n4", GraphEdgeKind.NORMALIZES_UNIT))
        current = "n4"
        next_number = 5
    direction = step["direction"]
    relation_id = f"n{next_number}"
    inputs = (current, "n2", "n3")
    with localcontext() as context:
        context.prec = 120
        relation_value = (
            Decimal(base_value) * Decimal(constant) * Decimal(multiplier)
            if direction == "MOLES_TO_ENTITIES"
            else Decimal(base_value) / (Decimal(constant) * Decimal(multiplier))
        )
    nodes.append(
        make_node(
            relation_id,
            GraphNodeKind.AVOGADRO_RELATION,
            "amount entity relation",
            operation=("MULTIPLY" if direction == "MOLES_TO_ENTITIES" else "DIVIDE"),
            input_node_ids=inputs,
            exact_inputs=(base_value, constant, multiplier),
            exact_output=str(relation_value),
            unit="entities" if direction == "MOLES_TO_ENTITIES" else "mol",
            dimension=(
                "ENTITY_COUNT" if direction == "MOLES_TO_ENTITIES" else "AMOUNT"
            ),
            metadata={"basis": step["basis"], "constant_exact": True},
        )
    )
    edges.extend(
        (
            make_edge(current, relation_id, GraphEdgeKind.DEPENDS_ON),
            make_edge("n2", relation_id, GraphEdgeKind.USES_FACT),
            make_edge("n3", relation_id, GraphEdgeKind.USES_FORMULA_TERM),
        )
    )
    current = relation_id
    next_number += 1
    output_factor = _from_base_factor(target_unit)
    if output_factor != "1":
        normalized_id = f"n{next_number}"
        relation_value = next(
            node.exact_output for node in nodes if node.node_id == current
        )
        nodes.append(
            make_node(
                normalized_id,
                GraphNodeKind.UNIT_NORMALIZATION,
                "normalize target amount",
                operation="MULTIPLY",
                input_node_ids=(current,),
                exact_inputs=(str(relation_value),),
                exact_output=str(Decimal(str(relation_value)) * Decimal(output_factor)),
                unit=target_unit,
                dimension=_dimension(target_unit),
                metadata={"factor": output_factor, "source_unit": "mol"},
            )
        )
        edges.append(make_edge(current, normalized_id, GraphEdgeKind.NORMALIZES_UNIT))
        current = normalized_id
        next_number += 1
    exact_result = result["result"]["exact_internal_value"]
    round_id = f"n{next_number}"
    nodes.append(
        make_node(
            round_id,
            GraphNodeKind.ROUND_DISPLAY,
            "display rounding",
            operation="ROUND_DISPLAY",
            input_node_ids=(current,),
            exact_inputs=(exact_result,),
            exact_output=exact_result,
            unit=target_unit,
            dimension=_dimension(target_unit),
            display_output=result["result"]["rendered_value"],
            policy_version=result["rounding_policy"],
        )
    )
    edges.append(make_edge(current, round_id, GraphEdgeKind.ROUNDS_FOR_DISPLAY))
    final_id = f"n{next_number + 1}"
    nodes.append(
        make_node(
            final_id,
            GraphNodeKind.FINAL_RESULT,
            "entity amount result",
            operation="IDENTITY",
            input_node_ids=(round_id,),
            exact_output=exact_result,
            unit=target_unit,
            dimension=_dimension(target_unit),
            display_output=result["result"]["rendered_value"],
        )
    )
    edges.append(make_edge(round_id, final_id, GraphEdgeKind.SUPPORTS_RESULT))
    return tuple(nodes), tuple(edges), final_id


def _source_nodes(result: dict[str, Any], nodes):
    factual = [
        node.node_id
        for node in nodes
        if node.kind in {GraphNodeKind.FACT_LOOKUP, GraphNodeKind.ATOMIC_WEIGHT_LOOKUP}
    ]
    source_nodes = []
    edges = []
    for index, source_hash in enumerate(result["source_hashes"], start=1):
        node_id = f"s{index}"
        source_nodes.append(
            make_node(
                node_id,
                GraphNodeKind.SOURCE_REFERENCE,
                "verified source",
                exact_output=source_hash,
                source_hashes=(source_hash,),
                metadata={"source_hash": source_hash},
            )
        )
        edges.extend(
            make_edge(node_id, target, GraphEdgeKind.CITES_SOURCE) for target in factual
        )
    return tuple(source_nodes), tuple(edges)


def _warning_nodes(result: dict[str, Any], root: str):
    nodes = []
    edges = []
    for index, warning in enumerate(result.get("warnings", ()), start=1):
        node_id = f"w{index}"
        nodes.append(
            make_node(
                node_id,
                GraphNodeKind.WARNING,
                warning,
                exact_output=warning,
                metadata={"warning_code": warning},
            )
        )
        edges.append(make_edge(node_id, root, GraphEdgeKind.WARNS_ABOUT))
    return tuple(nodes), tuple(edges)


def _verify_result_hash(result: dict[str, Any]) -> None:
    body = {key: value for key, value in result.items() if key != "result_hash"}
    if result.get("result_hash") != content_hash(body):
        raise ValueError("invalid educational source-result hash")


def _to_base(value: str, unit: str) -> tuple[str, str, str]:
    factors = {"kg": ("1000", "g"), "mmol": ("0.001", "mol")}
    factor, base = factors.get(unit, ("1", unit))
    return str(Decimal(value) * Decimal(factor)), base, factor


def _from_base_factor(unit: str) -> str:
    return {"kg": "0.001", "mmol": "1000"}.get(unit, "1")


def _dimension(unit: str | None) -> str | None:
    return {
        None: None,
        "": "DIMENSIONLESS",
        "g": "MASS",
        "kg": "MASS",
        "mol": "AMOUNT",
        "mmol": "AMOUNT",
        "g/mol": "MOLAR_MASS",
        "kg/mol": "MOLAR_MASS",
        "mol^-1": "INVERSE_AMOUNT",
        "entities": "ENTITY_COUNT",
    }.get(unit, "UNKNOWN")
