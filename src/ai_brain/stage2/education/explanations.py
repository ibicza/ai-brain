"""Structured deterministic bilingual explanations derived from verified graphs."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    ExplanationArtifact,
    ExplanationMode,
    ExplanationPlan,
    ExplanationSegment,
    ExplanationSegmentKind,
    GradingResult,
    GraphNodeKind,
)
from ai_brain.stage2.education.version import EDUCATIONAL_RENDERING_VERSION
from ai_brain.stage2.facts.canonical import content_hash


def build_explanation_plan(
    graph: EducationalDerivationGraph,
    *,
    language: str,
    mode: ExplanationMode,
) -> ExplanationPlan:
    if language not in {"ru", "en"}:
        raise ValueError("explanation language must be ru or en")
    if mode in {ExplanationMode.CHECK_ONLY, ExplanationMode.HINT_ONLY}:
        raise ValueError(f"{mode.value} requires its dedicated authority artifact")
    verify_derivation_graph(graph)
    nodes = _selected_nodes(graph, mode)
    segments = [_segment(ExplanationSegmentKind.HEADING)]
    for node in nodes:
        segments.append(_segment(_segment_kind(node.kind), node.node_id))
    segments.extend(
        _segment(ExplanationSegmentKind.SOURCE_CITATION, node.node_id)
        for node in graph.nodes
        if node.kind == GraphNodeKind.SOURCE_REFERENCE
    )
    segments.append(
        _segment(
            ExplanationSegmentKind.GRAPH_REFERENCE,
            graph.root_result_node_id,
            permitted_fields=("graph_hash", "source_result_hash"),
        )
    )
    body = {
        "graph_hash": graph.graph_hash,
        "source_result_hash": graph.source_result_hash,
        "language": language,
        "mode": mode,
        "segments": tuple(segments),
        "rendering_version": EDUCATIONAL_RENDERING_VERSION,
    }
    return ExplanationPlan(**body, plan_hash=content_hash(body))


def render_explanation(
    graph: EducationalDerivationGraph,
    *,
    language: str,
    mode: ExplanationMode = ExplanationMode.FULL,
    attempt_made: bool = False,
    session_id: str | None = None,
    session_state_hash: str | None = None,
) -> ExplanationArtifact:
    if mode == ExplanationMode.SOLUTION_AFTER_ATTEMPT and not attempt_made:
        raise ValueError("solution-after-attempt requires a submitted attempt")
    if mode == ExplanationMode.SOLUTION_AFTER_ATTEMPT and (
        not session_id or not session_state_hash
    ):
        raise ValueError("solution-after-attempt requires exact session authority")
    plan = build_explanation_plan(graph, language=language, mode=mode)
    return render_explanation_plan(
        plan,
        graph,
        session_id=session_id,
        session_state_hash=session_state_hash,
    )


def render_check_explanation(
    graph: EducationalDerivationGraph,
    grading: GradingResult,
    *,
    language: str,
) -> ExplanationArtifact:
    """Render CHECK_ONLY exclusively from a grading result, never the graph root."""
    verify_derivation_graph(graph)
    if grading.answer_graph_hash != graph.graph_hash:
        raise ValueError("grading result is bound to another answer graph")
    labels = {
        "ru": ("Проверка ответа", "Статус", "Баллы", "Первая ошибка", "Диагноз"),
        "en": ("Answer check", "Status", "Score", "First error", "Diagnosis"),
    }
    if language not in labels:
        raise ValueError("explanation language must be ru or en")
    heading, status, score, first, diagnosis = labels[language]
    lines = [
        heading,
        f"{status}: {grading.correctness_status.value}",
        f"{score}: {grading.score}/{grading.maximum_score}",
    ]
    if grading.first_incorrect_node:
        lines.append(f"{first}: {grading.first_incorrect_node}")
    if grading.error_diagnoses:
        lines.append(
            f"{diagnosis}: "
            + ", ".join(item.code.value for item in grading.error_diagnoses)
        )
    # CHECK_ONLY plans intentionally contain no value-bearing graph segment.
    segments = (
        _segment(ExplanationSegmentKind.HEADING),
        _segment(
            ExplanationSegmentKind.GRAPH_REFERENCE,
            permitted_fields=("grading_result_hash",),
        ),
    )
    plan_body = {
        "graph_hash": graph.graph_hash,
        "source_result_hash": graph.source_result_hash,
        "language": language,
        "mode": ExplanationMode.CHECK_ONLY,
        "segments": segments,
        "rendering_version": EDUCATIONAL_RENDERING_VERSION,
    }
    plan = ExplanationPlan(**plan_body, plan_hash=content_hash(plan_body))
    body = {
        "graph_hash": graph.graph_hash,
        "source_result_hash": graph.source_result_hash,
        "language": language,
        "mode": ExplanationMode.CHECK_ONLY,
        "text": "\n".join(lines),
        "numeric_node_ids": (),
        "formula_node_ids": (),
        "source_node_ids": (),
        "rendering_version": EDUCATIONAL_RENDERING_VERSION,
        "plan_hash": plan.plan_hash,
        "grading_result_hash": grading.result_hash,
        "session_id": None,
        "session_state_hash": None,
    }
    return ExplanationArtifact(**body, explanation_hash=content_hash(body))


def render_explanation_plan(
    plan: ExplanationPlan,
    graph: EducationalDerivationGraph,
    *,
    session_id: str | None = None,
    session_state_hash: str | None = None,
) -> ExplanationArtifact:
    verify_explanation_plan(plan, graph)
    text = _render_plan_text(plan, graph)
    nodes = {node.node_id: node for node in graph.nodes}
    selected_ids = tuple(
        node_id for segment in plan.segments for node_id in segment.node_ids
    )
    numeric = tuple(
        node_id
        for node_id in selected_ids
        if node_id in nodes and _has_numeric_output(nodes[node_id].exact_output)
    )
    formulas = tuple(
        node_id
        for node_id in selected_ids
        if node_id in nodes
        and (
            nodes[node_id].kind == GraphNodeKind.FORMULA_PARSE
            or nodes[node_id].metadata.get("value_type") == "formula"
        )
    )
    sources = tuple(
        node_id
        for node_id in selected_ids
        if node_id in nodes and nodes[node_id].kind == GraphNodeKind.SOURCE_REFERENCE
    )
    body = {
        "graph_hash": graph.graph_hash,
        "source_result_hash": graph.source_result_hash,
        "language": plan.language,
        "mode": plan.mode,
        "text": text,
        "numeric_node_ids": numeric,
        "formula_node_ids": formulas,
        "source_node_ids": sources,
        "rendering_version": EDUCATIONAL_RENDERING_VERSION,
        "plan_hash": plan.plan_hash,
        "grading_result_hash": None,
        "session_id": session_id,
        "session_state_hash": session_state_hash,
    }
    artifact = ExplanationArtifact(**body, explanation_hash=content_hash(body))
    verify_explanation(
        artifact,
        graph,
        plan=plan,
        session_id=session_id,
        session_state_hash=session_state_hash,
    )
    return artifact


def verify_explanation_plan(
    plan: ExplanationPlan, graph: EducationalDerivationGraph
) -> None:
    body = asdict(plan)
    digest = body.pop("plan_hash")
    if content_hash(body) != digest:
        raise ValueError("explanation plan hash mismatch")
    if (
        plan.graph_hash != graph.graph_hash
        or plan.source_result_hash != graph.source_result_hash
        or plan.rendering_version != EDUCATIONAL_RENDERING_VERSION
    ):
        raise ValueError("explanation plan dependency mismatch")
    nodes = {node.node_id: node for node in graph.nodes}
    seen_graph_reference = False
    ordered = {node.node_id: index for index, node in enumerate(graph.nodes)}
    previous_index = -1
    for segment in plan.segments:
        _verify_segment_hash(segment)
        if any(node_id not in nodes for node_id in segment.node_ids):
            raise ValueError("explanation plan references an unknown node")
        if segment.kind == ExplanationSegmentKind.GRAPH_REFERENCE:
            seen_graph_reference = True
        for node_id in segment.node_ids:
            node = nodes[node_id]
            if not _compatible(segment.kind, node.kind):
                raise ValueError("explanation segment/node type mismatch")
            index = ordered[node_id]
            if node.kind not in {GraphNodeKind.SOURCE_REFERENCE, GraphNodeKind.WARNING}:
                if index < previous_index:
                    raise ValueError("explanation plan violates graph order")
                previous_index = index
    if not seen_graph_reference:
        raise ValueError("explanation plan lacks its graph reference")
    if plan.mode in {
        ExplanationMode.CONCISE,
        ExplanationMode.FULL,
        ExplanationMode.SOLUTION_AFTER_ATTEMPT,
    }:
        canonical = build_explanation_plan(
            graph, language=plan.language, mode=plan.mode
        )
        if plan != canonical:
            raise ValueError("explanation plan is not the exact canonical plan")


def verify_explanation(
    artifact: ExplanationArtifact,
    graph: EducationalDerivationGraph,
    *,
    plan: ExplanationPlan | None = None,
    grading: GradingResult | None = None,
    session_id: str | None = None,
    session_state_hash: str | None = None,
) -> None:
    body = asdict(artifact)
    digest = body.pop("explanation_hash")
    if content_hash(body) != digest:
        raise ValueError("explanation hash mismatch")
    if artifact.mode == ExplanationMode.CHECK_ONLY:
        if plan is not None:
            raise ValueError("dedicated explanation modes cannot use a graph plan")
        if (
            artifact.numeric_node_ids
            or artifact.formula_node_ids
            or artifact.source_node_ids
        ):
            raise ValueError("dedicated explanation mode leaks graph values")
        if grading is None or artifact.grading_result_hash != grading.result_hash:
            raise ValueError("CHECK_ONLY explanation lacks exact grading authority")
        if artifact != render_check_explanation(
            graph, grading, language=artifact.language
        ):
            raise ValueError("CHECK_ONLY explanation is not reproducible")
        return
    if artifact.mode == ExplanationMode.HINT_ONLY:
        raise ValueError("HINT_ONLY is not a persisted explanation authority")
    if artifact.grading_result_hash is not None:
        raise ValueError("ordinary explanation has an unexpected grading binding")
    if artifact.mode == ExplanationMode.SOLUTION_AFTER_ATTEMPT:
        if (
            not session_id
            or not session_state_hash
            or artifact.session_id != session_id
            or artifact.session_state_hash != session_state_hash
        ):
            raise ValueError("solution explanation lacks exact session authority")
    elif artifact.session_id is not None or artifact.session_state_hash is not None:
        raise ValueError("ordinary explanation has an unexpected session binding")
    expected_plan = plan or build_explanation_plan(
        graph, language=artifact.language, mode=artifact.mode
    )
    verify_explanation_plan(expected_plan, graph)
    if artifact.plan_hash != expected_plan.plan_hash:
        raise ValueError("explanation references another plan")
    if artifact.text != _render_plan_text(expected_plan, graph):
        raise ValueError("trusted explanation contains unsupported content")
    nodes = {node.node_id: node for node in graph.nodes}
    selected_ids = tuple(
        node_id for segment in expected_plan.segments for node_id in segment.node_ids
    )
    expected_numeric = tuple(
        node_id
        for node_id in selected_ids
        if node_id in nodes and _has_numeric_output(nodes[node_id].exact_output)
    )
    expected_formulas = tuple(
        node_id
        for node_id in selected_ids
        if node_id in nodes
        and (
            nodes[node_id].kind == GraphNodeKind.FORMULA_PARSE
            or nodes[node_id].metadata.get("value_type") == "formula"
        )
    )
    expected_sources = tuple(
        node_id
        for node_id in selected_ids
        if node_id in nodes and nodes[node_id].kind == GraphNodeKind.SOURCE_REFERENCE
    )
    if (
        artifact.numeric_node_ids != expected_numeric
        or artifact.formula_node_ids != expected_formulas
        or artifact.source_node_ids != expected_sources
    ):
        raise ValueError("trusted explanation mappings are not reproducible")


def _segment(
    kind: ExplanationSegmentKind,
    *node_ids: str,
    permitted_fields: tuple[str, ...] = (
        "label",
        "operation",
        "exact_inputs",
        "exact_output",
        "unit",
        "display_output",
    ),
) -> ExplanationSegment:
    body = {
        "kind": kind,
        "node_ids": tuple(node_ids),
        "permitted_fields": permitted_fields,
    }
    return ExplanationSegment(**body, segment_hash=content_hash(body))


def _verify_segment_hash(segment: ExplanationSegment) -> None:
    body = asdict(segment)
    digest = body.pop("segment_hash")
    if content_hash(body) != digest:
        raise ValueError("explanation segment hash mismatch")


def _render_plan_text(plan: ExplanationPlan, graph: EducationalDerivationGraph) -> str:
    nodes = {node.node_id: node for node in graph.nodes}
    lines = []
    for segment in plan.segments:
        if segment.kind == ExplanationSegmentKind.HEADING:
            prefix = (
                "Проверенное объяснение"
                if plan.language == "ru"
                else "Verified explanation"
            )
            lines.append(f"{prefix}: {plan.mode.value}")
        elif segment.kind == ExplanationSegmentKind.GRAPH_REFERENCE:
            graph_label = "Граф" if plan.language == "ru" else "Graph"
            result_label = "Результат" if plan.language == "ru" else "Result"
            lines.extend(
                (
                    f"{graph_label}: {graph.graph_hash}",
                    f"{result_label}: {graph.source_result_hash}",
                )
            )
        else:
            lines.extend(
                _render_node(nodes[node_id], plan.language)
                for node_id in segment.node_ids
            )
    return "\n".join(lines)


def _render_node(node, language: str) -> str:
    label = _NODE_LABELS[language].get(node.kind, node.label)
    output = node.display_output or _value_text(node.exact_output)
    unit = f" {node.unit}" if node.unit else ""
    if node.operation:
        inputs = ", ".join(node.exact_inputs)
        return f"[{node.node_id}] {label}: {node.operation}({inputs}) = {output}{unit}."
    return f"[{node.node_id}] {label}: {output}{unit}."


def _selected_nodes(graph: EducationalDerivationGraph, mode: ExplanationMode):
    nodes = tuple(
        node for node in graph.nodes if node.kind != GraphNodeKind.SOURCE_REFERENCE
    )
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
    return nodes


def _segment_kind(kind: GraphNodeKind) -> ExplanationSegmentKind:
    mapping = {
        GraphNodeKind.GIVEN_VALUE: ExplanationSegmentKind.GIVEN,
        GraphNodeKind.FACT_LOOKUP: ExplanationSegmentKind.FACT,
        GraphNodeKind.ATOMIC_WEIGHT_LOOKUP: ExplanationSegmentKind.FACT,
        GraphNodeKind.FORMULA_PARSE: ExplanationSegmentKind.FORMULA,
        GraphNodeKind.FORMULA_COMPOSITION: ExplanationSegmentKind.INTERMEDIATE_RESULT,
        GraphNodeKind.ROUND_DISPLAY: ExplanationSegmentKind.ROUNDING,
        GraphNodeKind.FINAL_RESULT: ExplanationSegmentKind.FINAL_RESULT,
        GraphNodeKind.WARNING: ExplanationSegmentKind.WARNING,
    }
    return mapping.get(kind, ExplanationSegmentKind.OPERATION)


def _compatible(segment: ExplanationSegmentKind, node: GraphNodeKind) -> bool:
    if segment in {
        ExplanationSegmentKind.GRAPH_REFERENCE,
        ExplanationSegmentKind.HEADING,
    }:
        return True
    return _segment_kind(node) == segment or (
        segment == ExplanationSegmentKind.SOURCE_CITATION
        and node == GraphNodeKind.SOURCE_REFERENCE
    )


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
        GraphNodeKind.SOURCE_REFERENCE: "Источник",
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
        GraphNodeKind.SOURCE_REFERENCE: "Source",
    },
}
