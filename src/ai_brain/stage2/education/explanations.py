"""Deterministic bilingual explanations rendered only from verified graph nodes."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    ExplanationArtifact,
    ExplanationMode,
    GraphNodeKind,
)
from ai_brain.stage2.education.version import EDUCATIONAL_RENDERING_VERSION
from ai_brain.stage2.facts.canonical import content_hash


def render_explanation(
    graph: EducationalDerivationGraph,
    *,
    language: str,
    mode: ExplanationMode = ExplanationMode.FULL,
    attempt_made: bool = False,
) -> ExplanationArtifact:
    if language not in {"ru", "en"}:
        raise ValueError("explanation language must be ru or en")
    verify_derivation_graph(graph)
    if mode == ExplanationMode.SOLUTION_AFTER_ATTEMPT and not attempt_made:
        raise ValueError("solution-after-attempt requires a submitted attempt")
    selected = _selected_nodes(graph, mode)
    lines = [_heading(language, mode)]
    for node in selected:
        lines.append(_render_node(node, language))
    all_source_nodes = tuple(
        node for node in graph.nodes if node.kind == GraphNodeKind.SOURCE_REFERENCE
    )
    source_nodes = (
        ()
        if mode in {ExplanationMode.CHECK_ONLY, ExplanationMode.HINT_ONLY}
        else all_source_nodes
    )
    if source_nodes:
        label = "Источники" if language == "ru" else "Sources"
        lines.append(
            f"{label}: "
            + ", ".join(
                f"[{node.node_id}] {node.exact_output}" for node in source_nodes
            )
        )
    lines.append(("Граф" if language == "ru" else "Graph") + f": {graph.graph_hash}")
    lines.append(
        ("Результат" if language == "ru" else "Result")
        + f": {graph.source_result_hash}"
    )
    text = "\n".join(lines)
    numeric = tuple(
        node.node_id for node in selected if _has_numeric_output(node.exact_output)
    )
    formulas = tuple(
        node.node_id
        for node in selected
        if node.kind == GraphNodeKind.FORMULA_PARSE
        or (
            node.kind == GraphNodeKind.GIVEN_VALUE
            and node.metadata.get("value_type") == "formula"
        )
    )
    body = {
        "graph_hash": graph.graph_hash,
        "source_result_hash": graph.source_result_hash,
        "language": language,
        "mode": mode,
        "text": text,
        "numeric_node_ids": numeric,
        "formula_node_ids": formulas,
        "source_node_ids": tuple(node.node_id for node in source_nodes),
        "rendering_version": EDUCATIONAL_RENDERING_VERSION,
    }
    artifact = ExplanationArtifact(**body, explanation_hash=content_hash(body))
    verify_explanation(artifact, graph)
    return artifact


def verify_explanation(
    artifact: ExplanationArtifact, graph: EducationalDerivationGraph
) -> None:
    body = asdict(artifact)
    digest = body.pop("explanation_hash")
    if content_hash(body) != digest:
        raise ValueError("explanation hash mismatch")
    if (
        artifact.graph_hash != graph.graph_hash
        or artifact.source_result_hash != graph.source_result_hash
    ):
        raise ValueError("explanation is bound to another graph")
    nodes = {node.node_id: node for node in graph.nodes}
    referenced = set(
        artifact.numeric_node_ids + artifact.formula_node_ids + artifact.source_node_ids
    )
    if not referenced <= set(nodes):
        raise ValueError("explanation references an unknown node")
    for node_id in artifact.numeric_node_ids:
        if (
            str(nodes[node_id].exact_output) not in artifact.text
            and str(nodes[node_id].display_output or "") not in artifact.text
        ):
            raise ValueError("explanation numeric mapping is missing")
    for node_id in artifact.formula_node_ids:
        if str(nodes[node_id].exact_output) not in artifact.text:
            raise ValueError("explanation formula mapping is missing")
    for node_id in artifact.source_node_ids:
        if str(nodes[node_id].exact_output) not in artifact.text:
            raise ValueError("explanation citation is missing")
    root = nodes[graph.root_result_node_id]
    if artifact.mode not in {ExplanationMode.CHECK_ONLY, ExplanationMode.HINT_ONLY}:
        rendered = root.display_output or str(root.exact_output)
        if rendered not in artifact.text:
            raise ValueError("explanation final result is missing")


def _selected_nodes(graph: EducationalDerivationGraph, mode: ExplanationMode):
    nodes = tuple(
        node for node in graph.nodes if node.kind != GraphNodeKind.SOURCE_REFERENCE
    )
    root = next(node for node in nodes if node.node_id == graph.root_result_node_id)
    if mode == ExplanationMode.CONCISE:
        important = {
            GraphNodeKind.GIVEN_VALUE,
            GraphNodeKind.FORMULA_PARSE,
            GraphNodeKind.MOLE_RELATION,
            GraphNodeKind.AVOGADRO_RELATION,
            GraphNodeKind.FINAL_RESULT,
            GraphNodeKind.WARNING,
        }
        return tuple(node for node in nodes if node.kind in important)
    if mode == ExplanationMode.CHECK_ONLY:
        return (root,)
    if mode == ExplanationMode.HINT_ONLY:
        return tuple(
            node
            for node in nodes
            if node.kind
            not in {GraphNodeKind.FINAL_RESULT, GraphNodeKind.ROUND_DISPLAY}
        )[:1]
    return nodes


def _render_node(node, language: str) -> str:
    label = _NODE_LABELS[language].get(node.kind, node.label)
    output = node.display_output or _value_text(node.exact_output)
    unit = f" {node.unit}" if node.unit else ""
    if node.operation:
        inputs = ", ".join(node.exact_inputs)
        return f"[{node.node_id}] {label}: {node.operation}({inputs}) = {output}{unit}."
    return f"[{node.node_id}] {label}: {output}{unit}."


def _value_text(value) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}:{item}" for key, item in sorted(value.items()))
    return str(value)


def _has_numeric_output(value) -> bool:
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return isinstance(value, dict) and any(
        _has_numeric_output(item) for item in value.values()
    )


def _heading(language: str, mode: ExplanationMode) -> str:
    prefix = "Проверенное объяснение" if language == "ru" else "Verified explanation"
    return f"{prefix}: {mode.value}"


_NODE_LABELS = {
    "ru": {
        GraphNodeKind.GIVEN_VALUE: "Дано",
        GraphNodeKind.FACT_LOOKUP: "Проверенный факт",
        GraphNodeKind.FORMULA_PARSE: "Разбор формулы",
        GraphNodeKind.FORMULA_COMPOSITION: "Состав формулы",
        GraphNodeKind.STOICHIOMETRIC_COUNT: "Коэффициент",
        GraphNodeKind.UNIT_NORMALIZATION: "Перевод единиц",
        GraphNodeKind.ATOMIC_WEIGHT_LOOKUP: "Атомная масса",
        GraphNodeKind.MULTIPLY: "Вклад элемента",
        GraphNodeKind.ADD: "Сумма",
        GraphNodeKind.MOLE_RELATION: "Связь массы и количества",
        GraphNodeKind.AVOGADRO_RELATION: "Связь с постоянной Авогадро",
        GraphNodeKind.ROUND_DISPLAY: "Округление для отображения",
        GraphNodeKind.FINAL_RESULT: "Ответ",
        GraphNodeKind.WARNING: "Предупреждение",
    },
    "en": {
        GraphNodeKind.GIVEN_VALUE: "Given",
        GraphNodeKind.FACT_LOOKUP: "Verified fact",
        GraphNodeKind.FORMULA_PARSE: "Formula parse",
        GraphNodeKind.FORMULA_COMPOSITION: "Formula composition",
        GraphNodeKind.STOICHIOMETRIC_COUNT: "Coefficient",
        GraphNodeKind.UNIT_NORMALIZATION: "Unit conversion",
        GraphNodeKind.ATOMIC_WEIGHT_LOOKUP: "Atomic weight",
        GraphNodeKind.MULTIPLY: "Element contribution",
        GraphNodeKind.ADD: "Sum",
        GraphNodeKind.MOLE_RELATION: "Mass-amount relation",
        GraphNodeKind.AVOGADRO_RELATION: "Avogadro relation",
        GraphNodeKind.ROUND_DISPLAY: "Display rounding",
        GraphNodeKind.FINAL_RESULT: "Answer",
        GraphNodeKind.WARNING: "Warning",
    },
}
