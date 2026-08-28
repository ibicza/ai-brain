"""Independent chemistry counterfactuals used as diagnosis evidence."""

from __future__ import annotations

import re
from decimal import Decimal, localcontext
from functools import partial

from ai_brain.stage2.education.models import (
    CounterfactualAnswer,
    EducationalDerivationGraph,
    GraphNodeKind,
    MisconceptionCode,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.trusted_decimal import render_bounded_decimal


def chemistry_counterfactuals(
    graph: EducationalDerivationGraph,
) -> tuple[CounterfactualAnswer, ...]:
    root = next(
        node for node in graph.nodes if node.node_id == graph.root_result_node_id
    )
    candidates: list[tuple[MisconceptionCode, object, tuple[str, ...]]] = []
    if isinstance(root.exact_output, dict):
        if {"lower", "upper"} <= root.exact_output.keys():
            lower = Decimal(root.exact_output["lower"])
            upper = Decimal(root.exact_output["upper"])
            midpoint = (lower + upper) / Decimal(2)
            candidates.append(
                (
                    MisconceptionCode.INTERVAL_COLLAPSED_TO_MIDPOINT,
                    {
                        "lower": render_bounded_decimal(midpoint),
                        "upper": render_bounded_decimal(midpoint),
                    },
                    (root.node_id,),
                )
            )
        else:
            composition = dict(root.exact_output)
            candidates.extend(
                (
                    (
                        MisconceptionCode.SUBSCRIPT_IGNORED,
                        {key: 1 for key in composition},
                        (root.node_id,),
                    ),
                    (
                        MisconceptionCode.ELEMENT_COUNT_WRONG,
                        _changed_count(composition),
                        (root.node_id,),
                    ),
                )
            )
            grouped = _group_multiplier_counts(graph, composition)
            if grouped is not None:
                candidates.append(
                    (
                        MisconceptionCode.GROUP_MULTIPLIER_IGNORED,
                        grouped,
                        (root.node_id,),
                    )
                )
    facts = [
        node for node in graph.nodes if node.kind == GraphNodeKind.ATOMIC_WEIGHT_LOOKUP
    ]
    contributions = [
        node for node in graph.nodes if node.kind == GraphNodeKind.MULTIPLY
    ]
    if facts and contributions:
        ignored = sum((Decimal(str(node.exact_output)) for node in facts), Decimal(0))
        candidates.append(
            (
                MisconceptionCode.SUBSCRIPT_IGNORED,
                ignored,
                tuple(node.node_id for node in facts),
            )
        )
        if len(contributions) > 1:
            candidates.append(
                (
                    MisconceptionCode.MOLAR_MASS_SUM_WRONG,
                    Decimal(str(contributions[0].exact_output)),
                    (contributions[0].node_id,),
                )
            )
        first_fact = facts[0]
        first_contribution = contributions[0]
        wrong_weight_total = sum(
            (Decimal(str(node.exact_output)) for node in contributions), Decimal(0)
        ) + Decimal(1)
        if root.unit == "kg/mol":
            wrong_weight_total *= Decimal("0.001")
        candidates.extend(
            (
                (
                    MisconceptionCode.ATOMIC_WEIGHT_WRONG,
                    wrong_weight_total,
                    (first_fact.node_id,),
                ),
                (
                    MisconceptionCode.MOLAR_MASS_TERM_WRONG,
                    wrong_weight_total,
                    (first_contribution.node_id,),
                ),
            )
        )
        grouped_mass = _group_multiplier_mass(graph, facts)
        if grouped_mass is not None:
            if root.unit == "kg/mol":
                grouped_mass *= Decimal("0.001")
            candidates.append(
                (
                    MisconceptionCode.GROUP_MULTIPLIER_IGNORED,
                    grouped_mass,
                    tuple(node.node_id for node in facts),
                )
            )
    relation = next(
        (
            node
            for node in graph.nodes
            if node.kind
            in {GraphNodeKind.MOLE_RELATION, GraphNodeKind.AVOGADRO_RELATION}
        ),
        None,
    )
    if relation is not None:
        inputs = [Decimal(value) for value in relation.exact_inputs]
        if relation.operation == "DIVIDE":
            wrong = inputs[0] * inputs[1]
            code = MisconceptionCode.MULTIPLY_INSTEAD_OF_DIVIDE
        else:
            wrong = inputs[0] / inputs[1]
            code = MisconceptionCode.DIVIDE_INSTEAD_OF_MULTIPLY
        candidates.append((code, wrong, relation.input_node_ids))
        if relation.kind == GraphNodeKind.AVOGADRO_RELATION:
            constant = inputs[1]
            multiplier = inputs[2] if len(inputs) == 3 else Decimal(1)
            missing_constant = (
                inputs[0] * multiplier
                if relation.operation == "MULTIPLY"
                else inputs[0] / multiplier
            )
            candidates.append(
                (
                    MisconceptionCode.AVOGADRO_FACTOR_MISSING,
                    missing_constant,
                    (relation.input_node_ids[0],),
                )
            )
            candidates.append(
                (
                    MisconceptionCode.AVOGADRO_FACTOR_EXTRA,
                    Decimal(str(root.exact_output)) * constant,
                    (relation.node_id,),
                )
            )
            if multiplier != 1:
                missing_multiplier = (
                    inputs[0] * constant
                    if relation.operation == "MULTIPLY"
                    else inputs[0] / constant
                )
                code = (
                    MisconceptionCode.TARGET_ELEMENT_MULTIPLIER_WRONG
                    if relation.metadata.get("basis") == "ATOMS_OF_ELEMENT_IN_FORMULA"
                    else MisconceptionCode.FORMULA_ENTITY_ATOM_MULTIPLIER_MISSING
                )
                candidates.append(
                    (code, missing_multiplier, (relation.input_node_ids[2],))
                )
    if root.unit in {"g", "kg"}:
        candidates.append(
            (
                MisconceptionCode.GRAM_KILOGRAM_CONVERSION_ERROR,
                Decimal(str(root.exact_output)) * Decimal(1000),
                (root.node_id,),
            )
        )
    if root.unit in {"mol", "mmol"}:
        candidates.append(
            (
                MisconceptionCode.MOL_MMOL_CONVERSION_ERROR,
                Decimal(str(root.exact_output)) * Decimal(1000),
                (root.node_id,),
            )
        )
    result = []
    with localcontext() as context:
        context.prec = 120
        for code, value, node_ids in candidates:
            if isinstance(value, dict):
                answer = (
                    value
                    if {"lower", "upper"} <= value.keys()
                    else {"element_counts": dict(sorted(value.items()))}
                )
            else:
                answer = {
                    "value": render_bounded_decimal(value),
                    "unit": root.unit,
                }
            body = {
                "diagnosis": code,
                "answer": answer,
                "matching_node_ids": node_ids,
            }
            result.append(
                CounterfactualAnswer(**body, counterfactual_hash=content_hash(body))
            )
    unique = {}
    for item in result:
        unique[(item.diagnosis, content_hash(item.answer))] = item
    return tuple(unique.values())


def _changed_count(composition: dict[str, int]) -> dict[str, int]:
    changed = dict(composition)
    first = min(changed)
    changed[first] += 1
    return changed


def _group_multiplier_counts(
    graph: EducationalDerivationGraph, composition: dict[str, int]
) -> dict[str, int] | None:
    parsed = next(
        (node for node in graph.nodes if node.kind == GraphNodeKind.FORMULA_PARSE), None
    )
    if parsed is None:
        return None
    match = re.search(r"\(([A-Za-z0-9]+)\)([2-9][0-9]*)", str(parsed.exact_output))
    if match is None:
        return None
    multiplier = int(match.group(2))
    group_counts: dict[str, int] = {}
    for symbol, count_text in re.findall(r"([A-Z][a-z]?)([0-9]*)", match.group(1)):
        group_counts[symbol] = group_counts.get(symbol, 0) + int(count_text or "1")
    changed = dict(composition)
    for symbol, count in group_counts.items():
        changed[symbol] -= count * (multiplier - 1)
    return changed


def _group_multiplier_mass(
    graph: EducationalDerivationGraph, facts: list
) -> Decimal | None:
    parsed = next(
        (node for node in graph.nodes if node.kind == GraphNodeKind.FORMULA_PARSE), None
    )
    if parsed is None:
        return None
    composition = dict(parsed.metadata.get("composition", {}))
    changed = _group_multiplier_counts(graph, composition)
    if changed is None:
        return None
    weights = {
        node.metadata["symbol"]: Decimal(str(node.exact_output)) for node in facts
    }
    return sum(
        (weights[symbol] * count for symbol, count in changed.items()), Decimal(0)
    )


def calculate_misconception_counterfactual(
    code: MisconceptionCode,
    graph: EducationalDerivationGraph,
) -> tuple[CounterfactualAnswer, ...]:
    """Return exact candidates for one taxonomy code, or empty when inapplicable."""
    return tuple(
        item for item in chemistry_counterfactuals(graph) if item.diagnosis == code
    )


COUNTERFACTUAL_CALCULATORS = {
    code: partial(calculate_misconception_counterfactual, code)
    for code in MisconceptionCode
    if code
    not in {
        MisconceptionCode.AMBIGUOUS_DIAGNOSIS,
        MisconceptionCode.UNCLASSIFIED_ERROR,
    }
}
