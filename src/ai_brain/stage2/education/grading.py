"""Exact final-answer and graph-node grading."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ai_brain.stage2.education.answers import numeric_equivalent, parse_unit
from ai_brain.stage2.education.diagnosis import diagnose_answer
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import (
    AnswerParseStatus,
    EducationalDerivationGraph,
    ExerciseInstance,
    GradingResult,
    GradingStatus,
    GraphNodeKind,
    StudentAnswer,
)
from ai_brain.stage2.education.version import GRADING_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage2.trusted_decimal import parse_bounded_decimal


def grade_answer(
    instance: ExerciseInstance,
    answer: StudentAnswer,
    graph: EducationalDerivationGraph,
    *,
    attempt_id: str,
    created_at: str | None = None,
) -> GradingResult:
    verify_derivation_graph(graph)
    if instance.hidden_answer_graph_hash != graph.graph_hash:
        return _result(
            instance,
            answer,
            graph,
            attempt_id,
            GradingStatus.STALE_EXERCISE,
            "0",
            (),
            (),
            None,
            (),
            "NOT_COMPARED",
            "NOT_COMPARED",
            created_at,
        )
    if (
        answer.parse_status != AnswerParseStatus.PARSED
        or answer.interpreted_answer is None
    ):
        status = (
            GradingStatus.AMBIGUOUS_ANSWER
            if answer.parse_status == AnswerParseStatus.REQUIRES_CONFIRMATION
            else GradingStatus.INVALID_ANSWER
        )
        diagnoses = diagnose_answer(instance, answer)
        return _result(
            instance,
            answer,
            graph,
            attempt_id,
            status,
            "0",
            (),
            (),
            None,
            diagnoses,
            "NOT_COMPARED",
            "NOT_COMPARED",
            created_at,
        )
    if "steps" in answer.interpreted_answer:
        return _grade_steps(instance, answer, graph, attempt_id, created_at)
    correct, equivalent_unit, rounding, score = _compare_final(
        answer.interpreted_answer, instance.hidden_expected_answer
    )
    if correct:
        status = (
            GradingStatus.CORRECT_EQUIVALENT_UNIT
            if equivalent_unit
            else GradingStatus.CORRECT_WITH_ACCEPTABLE_ROUNDING
            if rounding == "ACCEPTABLE"
            else GradingStatus.CORRECT
        )
        diagnoses = ()
        correct_nodes = (graph.root_result_node_id,)
        incorrect_nodes = ()
    else:
        status = (
            GradingStatus.PARTIALLY_CORRECT
            if Decimal(score) > 0
            else GradingStatus.INCORRECT
        )
        diagnoses = diagnose_answer(instance, answer)
        correct_nodes = ()
        incorrect_nodes = (graph.root_result_node_id,)
    return _result(
        instance,
        answer,
        graph,
        attempt_id,
        status,
        score,
        correct_nodes,
        incorrect_nodes,
        incorrect_nodes[0] if incorrect_nodes else None,
        diagnoses,
        "EQUIVALENT" if equivalent_unit else "SAME" if correct else "DIFFERENT",
        rounding,
        created_at,
    )


def _compare_final(
    actual: dict[str, Any], expected: dict[str, Any]
) -> tuple[bool, bool, str, str]:
    if {"value", "unit"} <= expected.keys() and {"value", "unit"} <= actual.keys():
        try:
            equal, equivalent_unit = numeric_equivalent(
                actual["value"], actual["unit"], expected["value"], expected["unit"]
            )
        except (TypeError, ValueError):
            return False, False, "NOT_APPLICABLE", "0"
        if equal:
            return True, equivalent_unit, "EXACT", "1"
        tolerance = expected.get("absolute_tolerance")
        if tolerance is not None:
            source = parse_unit(actual["unit"])
            target = parse_unit(expected["unit"])
            if source.dimension == target.dimension:
                from ai_brain.stage2.education.answers import convert_exact

                difference = abs(
                    convert_exact(actual["value"], actual["unit"], expected["unit"])
                    - parse_bounded_decimal(expected["value"])
                )
                if difference <= parse_bounded_decimal(tolerance):
                    return True, source.canonical != target.canonical, "ACCEPTABLE", "1"
        return False, False, "OUTSIDE_POLICY", "0"
    if "element_counts" in expected and "element_counts" in actual:
        expected_map = expected["element_counts"]
        actual_map = actual["element_counts"]
        if actual_map == expected_map:
            return True, False, "NOT_APPLICABLE", "1"
        union = set(expected_map) | set(actual_map)
        matched = sum(expected_map.get(key) == actual_map.get(key) for key in union)
        return (
            False,
            False,
            "NOT_APPLICABLE",
            str(Decimal(matched) / Decimal(max(1, len(union)))),
        )
    if {"lower", "upper"} <= expected.keys() and {"lower", "upper"} <= actual.keys():
        equal = all(
            parse_bounded_decimal(actual[key]) == parse_bounded_decimal(expected[key])
            for key in ("lower", "upper")
        )
        return (
            equal,
            False,
            "EXACT" if equal else "OUTSIDE_POLICY",
            "1" if equal else "0",
        )
    if actual == expected:
        return True, False, "NOT_APPLICABLE", "1"
    return False, False, "NOT_APPLICABLE", "0"


def _grade_steps(instance, answer, graph, attempt_id, created_at):
    expected_nodes = tuple(
        node
        for node in graph.nodes
        if node.kind
        in {
            GraphNodeKind.MULTIPLY,
            GraphNodeKind.ADD,
            GraphNodeKind.DIVIDE,
            GraphNodeKind.UNIT_NORMALIZATION,
            GraphNodeKind.MOLE_RELATION,
            GraphNodeKind.AVOGADRO_RELATION,
        }
    )
    submitted = answer.interpreted_answer["steps"]
    correct_nodes = []
    incorrect_nodes = []
    for index, node in enumerate(expected_nodes):
        if index >= len(submitted):
            incorrect_nodes.append(node.node_id)
            continue
        step = submitted[index]
        operands_match = len(step["operands"]) == len(node.exact_inputs) and all(
            parse_bounded_decimal(actual) == parse_bounded_decimal(expected)
            for actual, expected in zip(
                step["operands"], node.exact_inputs, strict=True
            )
        )
        valid = (
            step["operation"] == (node.operation or "").upper()
            and operands_match
            and parse_bounded_decimal(step["output"])
            == parse_bounded_decimal(node.exact_output)
            and step["unit"] == node.unit
        )
        (correct_nodes if valid else incorrect_nodes).append(node.node_id)
    if len(submitted) > len(expected_nodes):
        incorrect_nodes.extend(
            f"submitted:{index}" for index in range(len(expected_nodes), len(submitted))
        )
    maximum = max(1, len(expected_nodes))
    score = str(Decimal(len(correct_nodes)) / Decimal(maximum))
    root = next(
        node for node in graph.nodes if node.node_id == graph.root_result_node_id
    )
    final_correct = any(
        parse_bounded_decimal(step["output"])
        == parse_bounded_decimal(root.exact_output)
        and step["unit"] == root.unit
        for step in submitted
    )
    if not incorrect_nodes and len(submitted) == len(expected_nodes):
        status = GradingStatus.CORRECT
    elif final_correct:
        status = GradingStatus.CORRECT_FINAL_UNVERIFIED_STEPS
    elif correct_nodes:
        status = GradingStatus.PARTIALLY_CORRECT
    else:
        status = GradingStatus.INCORRECT
    diagnoses = (
        () if status == GradingStatus.CORRECT else diagnose_answer(instance, answer)
    )
    return _result(
        instance,
        answer,
        graph,
        attempt_id,
        status,
        score,
        tuple(correct_nodes),
        tuple(incorrect_nodes),
        incorrect_nodes[0] if incorrect_nodes else None,
        diagnoses,
        "STEP_UNITS",
        "STEP_OUTPUTS",
        created_at,
    )


def _result(
    instance,
    answer,
    graph,
    attempt_id,
    status,
    score,
    correct_nodes,
    incorrect_nodes,
    first,
    diagnoses,
    unit_comparison,
    rounding_comparison,
    created_at,
):
    body = {
        "attempt_id": attempt_id,
        "exercise_id": instance.instance_id,
        "exercise_hash": instance.instance_hash,
        "student_answer_hash": answer.answer_hash,
        "interpreted_answer": answer.interpreted_answer,
        "parse_status": answer.parse_status,
        "correctness_status": status,
        "score": score,
        "maximum_score": "1",
        "correct_nodes": correct_nodes,
        "incorrect_nodes": incorrect_nodes,
        "first_incorrect_node": first,
        "error_diagnoses": diagnoses,
        "unit_comparison": unit_comparison,
        "rounding_comparison": rounding_comparison,
        "answer_graph_hash": graph.graph_hash,
        "created_at": created_at or utc_now(),
        "schema_version": GRADING_SCHEMA_VERSION,
    }
    return GradingResult(**body, result_hash=content_hash(body))
