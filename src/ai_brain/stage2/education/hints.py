"""Bounded five-level hints derived from a verified answer graph."""

from __future__ import annotations

from ai_brain.stage2.education.explanations import render_explanation
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.hint_validation import verify_hint_no_answer_leakage
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    ErrorDiagnosis,
    ExplanationMode,
    GraphNodeKind,
    HintArtifact,
    HintLevel,
    HintPlan,
    MisconceptionCode,
)
from ai_brain.stage2.education.version import HINT_POLICY_VERSION
from ai_brain.stage2.facts.canonical import content_hash

GENERIC_ONLY = "GENERIC_ONLY"
TARGETED_HINT_STRATEGIES = {
    code: (
        GENERIC_ONLY
        if code
        in {
            MisconceptionCode.UNCLASSIFIED_ERROR,
            MisconceptionCode.AMBIGUOUS_DIAGNOSIS,
            MisconceptionCode.ARITHMETIC_ERROR,
        }
        else f"TARGET_{code.value}"
    )
    for code in MisconceptionCode
}


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
    targeted_codes = tuple(
        item.code for item in diagnoses if item.confidence.value == "EXACT_MATCH"
    )
    if level == HintLevel.FULL_SOLUTION:
        text = render_explanation(
            graph, language=language, mode=ExplanationMode.FULL
        ).text
        revealed = plan.node_order
        final_revealed = True
    else:
        text, revealed = _bounded_hint(graph, level, language, targeted_codes)
        final_revealed = False
        verify_hint_no_answer_leakage(text, root)
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
        operation = target.operation or target.kind.value
        return (
            "Следующий проверенный шаг" if language == "ru" else "Next verified step"
        ) + f": {operation} — {target.label}.", ()
    if level == HintLevel.SUBSTITUTION:
        return (
            "Подставь значения" if language == "ru" else "Substitute the values"
        ) + ": " + ", ".join(target.exact_inputs) + ".", tuple(target.input_node_ids)
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
    targeted = next(
        (code for code in codes if TARGETED_HINT_STRATEGIES[code] != GENERIC_ONLY),
        None,
    )
    if targeted is not None:
        return (
            f"Проверь шаг, связанный с категорией {targeted.value}."
            if language == "ru"
            else f"Recheck the step associated with {targeted.value}."
        )
    return ""
