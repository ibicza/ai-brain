"""Bounded route-level clarification construction."""

from __future__ import annotations

from uuid import uuid4

from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage2.router.models import (
    ClarificationKind,
    ClarificationRequest,
    RouteDecision,
)

_QUESTIONS = {
    ClarificationKind.FACT_OR_SKILL: (
        "Вы хотите получить сохранённый факт или выполнить действие?",
        "Do you want a stored fact or an action to be executed?",
    ),
    ClarificationKind.FACT_OR_TOOL: (
        "Нужно вычислить значение или найти уже сохранённое значение?",
        "Should the value be calculated or retrieved from stored facts?",
    ),
    ClarificationKind.SKILL_OR_TOOL: (
        "Нужно выполнить сохранённый навык или локальное вычисление?",
        "Should a stored skill or a local calculation be used?",
    ),
    ClarificationKind.MULTIPLE_FACT_ENTITIES: (
        "Какую сущность с таким именем вы имеете в виду?",
        "Which entity with that name do you mean?",
    ),
    ClarificationKind.UNKNOWN_FACT_PREDICATE: (
        "Какой точный предикат факта требуется?",
        "Which exact fact predicate is required?",
    ),
    ClarificationKind.MISSING_SKILL_DESTINATION: (
        "Укажите точное назначение действия.",
        "Specify the exact action destination.",
    ),
    ClarificationKind.MISSING_TOOL_ARGUMENT: (
        "Укажите недостающий аргумент инструмента.",
        "Provide the missing tool argument.",
    ),
    ClarificationKind.MULTI_INTENT: (
        "Разделите запрос на одно намерение за раз.",
        "Split the request into one intent at a time.",
    ),
    ClarificationKind.UNSUPPORTED_OPERATION: (
        "Уточните запрос в поддерживаемом контролируемом формате.",
        "Restate the request in a supported controlled form.",
    ),
}


def make_clarification(
    decision: RouteDecision,
    kind: ClarificationKind,
    *,
    missing_field: str,
    round_number: int = 1,
    clock=utc_now,
) -> ClarificationRequest:
    if round_number != 1:
        raise ValueError("only one bounded clarification round is supported")
    ru, en = _QUESTIONS[kind]
    body = {
        "clarification_id": f"clarification_{uuid4().hex}",
        "request_id": decision.request_id,
        "route_decision_hash": decision.route_decision_hash,
        "kind": kind,
        "missing_field": missing_field,
        "question_ru": ru,
        "question_en": en,
        "round_number": round_number,
        "created_at": clock(),
    }
    return ClarificationRequest(**body, clarification_hash=content_hash(body))
