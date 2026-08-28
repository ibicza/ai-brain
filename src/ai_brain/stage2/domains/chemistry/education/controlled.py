"""Exact bilingual routing for bounded educational requests."""

from __future__ import annotations

import re

from ai_brain.stage2.education.models import EducationalRoute, EducationalRouteKind
from ai_brain.stage2.facts.canonical import content_hash


def parse_educational_request(text: str, language: str) -> EducationalRoute:
    if language not in {"ru", "en"} or not isinstance(text, str) or len(text) > 512:
        raise ValueError("invalid educational controlled-language request")
    normalized = " ".join(text.strip().split())
    patterns = _patterns(language)
    for kind, pattern in patterns:
        match = re.fullmatch(pattern, normalized, flags=re.IGNORECASE)
        if match:
            payload = {key: value for key, value in match.groupdict().items() if value}
            body = {
                "kind": kind,
                "language": language,
                "payload": payload,
                "parser_evidence": {
                    "parser": "educational_controlled_v2",
                    "pattern": kind.value,
                },
            }
            return EducationalRoute(**body, route_hash=content_hash(body))
    body = {
        "kind": EducationalRouteKind.UNSUPPORTED,
        "language": language,
        "payload": {},
        "parser_evidence": {"parser": "educational_controlled_v2"},
    }
    return EducationalRoute(**body, route_hash=content_hash(body))


def _patterns(language: str):
    if language == "ru":
        return (
            (
                EducationalRouteKind.EXPLAIN,
                r"Объясни,? как вычисляется молярная масса (?P<formula>[A-Za-z0-9()]+)\.?",
            ),
            (
                EducationalRouteKind.GENERATE_EXERCISE,
                r"Дай мне задачу на молярную массу\.?",
            ),
            (
                EducationalRouteKind.CHECK_ANSWER,
                r"Проверь мой ответ:\s*(?P<answer>.+)",
            ),
            (EducationalRouteKind.HINT, r"Дай подсказку\.?"),
            (EducationalRouteKind.SHOW_SOLUTION, r"Покажи полное решение\.?"),
        )
    return (
        (
            EducationalRouteKind.EXPLAIN,
            r"Explain how to calculate the molar mass of (?P<formula>[A-Za-z0-9()]+)\.?",
        ),
        (
            EducationalRouteKind.GENERATE_EXERCISE,
            r"Give me a molar-mass exercise\.?",
        ),
        (
            EducationalRouteKind.CHECK_ANSWER,
            r"Check my answer:\s*(?P<answer>.+)",
        ),
        (EducationalRouteKind.HINT, r"Give me a hint\.?"),
        (EducationalRouteKind.SHOW_SOLUTION, r"Show the full solution\.?"),
    )
