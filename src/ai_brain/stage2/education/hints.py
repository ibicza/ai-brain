"""Bounded five-level hints derived from a verified answer graph."""

from __future__ import annotations

from ai_brain.stage2.education.explanations import render_explanation
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    ErrorDiagnosis,
    ExplanationMode,
    GraphNodeKind,
    HintArtifact,
    HintLevel,
    HintPlan,
)
from ai_brain.stage2.education.version import HINT_POLICY_VERSION
from ai_brain.stage2.facts.canonical import content_hash


def build_hint_plan(exercise_id: str, graph: EducationalDerivationGraph) -> HintPlan:
    verify_derivation_graph(graph)
    node_order = tuple(
        node.node_id
        for node in graph.nodes
        if node.kind not in {GraphNodeKind.SOURCE_REFERENCE, GraphNodeKind.WARNING}
    )
    body = {
        "exercise_id": exercise_id,
        "graph_hash": graph.graph_hash,
        "node_order": node_order,
        "policy_version": HINT_POLICY_VERSION,
    }
    return HintPlan(**body, plan_hash=content_hash(body))


def render_hint(
    plan: HintPlan,
    graph: EducationalDerivationGraph,
    level: HintLevel,
    *,
    language: str,
    diagnoses: tuple[ErrorDiagnosis, ...] = (),
) -> HintArtifact:
    if language not in {"ru", "en"} or plan.graph_hash != graph.graph_hash:
        raise ValueError("hint request is incompatible with its graph")
    verify_derivation_graph(graph)
    root = next(
        node for node in graph.nodes if node.node_id == graph.root_result_node_id
    )
    diagnosis_codes = tuple(item.code for item in diagnoses)
    if level == HintLevel.FULL_SOLUTION:
        text = render_explanation(
            graph, language=language, mode=ExplanationMode.FULL
        ).text
        revealed = plan.node_order
        final_revealed = True
    else:
        text, revealed = _bounded_hint(graph, level, language, diagnosis_codes)
        final_revealed = False
        forbidden = {str(root.exact_output), str(root.display_output or "")}
        if any(value and value in text for value in forbidden):
            raise ValueError("early hint leaks the final answer")
    body = {
        "exercise_id": plan.exercise_id,
        "graph_hash": graph.graph_hash,
        "level": level,
        "language": language,
        "text": text,
        "revealed_node_ids": revealed,
        "diagnosis_codes": diagnosis_codes,
        "final_answer_revealed": final_revealed,
        "policy_version": HINT_POLICY_VERSION,
    }
    return HintArtifact(**body, hint_hash=content_hash(body))


def _bounded_hint(graph, level, language, diagnosis_codes):
    nodes = tuple(
        node
        for node in graph.nodes
        if node.kind
        not in {
            GraphNodeKind.FINAL_RESULT,
            GraphNodeKind.ROUND_DISPLAY,
            GraphNodeKind.SOURCE_REFERENCE,
            GraphNodeKind.WARNING,
        }
    )
    target = next((node for node in nodes if node.operation), nodes[0])
    targeted = _targeted_text(language, diagnosis_codes)
    if level == HintLevel.ORIENT:
        return targeted or (
            "Определи тип величины и нужное химическое соотношение."
            if language == "ru"
            else "Identify the quantity type and the required chemistry relation."
        ), ()
    if level == HintLevel.NEXT_STEP:
        return (
            "Следующий шаг" if language == "ru" else "Next step"
        ) + f": {target.kind.value}.", ()
    if level == HintLevel.SUBSTITUTION:
        return (
            "Используй входы узлов" if language == "ru" else "Use inputs from nodes"
        ) + ": " + ", ".join(target.input_node_ids) + ".", tuple(target.input_node_ids)
    safe = next(
        (
            node
            for node in nodes
            if node.exact_output
            != next(
                item.exact_output
                for item in graph.nodes
                if item.node_id == graph.root_result_node_id
            )
        ),
        None,
    )
    if safe is None:
        return (
            "Проверь исходный подтверждённый факт."
            if language == "ru"
            else "Review the original verified fact."
        ), ()
    return (
        ("Промежуточный результат" if language == "ru" else "Intermediate result")
        + f" [{safe.node_id}]: {safe.exact_output}{' ' + safe.unit if safe.unit else ''}.",
        (safe.node_id,),
    )


def _targeted_text(language, codes):
    names = {code.value for code in codes}
    if "GROUP_MULTIPLIER_IGNORED" in names:
        return (
            "Проверь множитель после скобок."
            if language == "ru"
            else "Check the multiplier after the group."
        )
    if "UNIT_WRONG_DIMENSION" in names:
        return (
            "Проверь размерность требуемой единицы."
            if language == "ru"
            else "Check the requested unit dimension."
        )
    if "MULTIPLY_INSTEAD_OF_DIVIDE" in names:
        return (
            "Для фиксированной массы проверь, как молярная масса входит в n = m/M."
            if language == "ru"
            else "For fixed mass, check how molar mass appears in n = m/M."
        )
    return ""
