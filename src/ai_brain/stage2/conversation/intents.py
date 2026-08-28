"""Deterministic finite RU/EN intent recognition; user text is data only."""

from __future__ import annotations

import re

from ai_brain.stage2.conversation.models import ConversationIntent, ParsedIntent
from ai_brain.stage2.conversation.version import CONTROLLED_INTENT_VERSION
from ai_brain.stage2.facts.canonical import content_hash

MAX_TEXT = 4096
PATTERNS = {
    ConversationIntent.START_TUTORING: (
        r"^(начать|начни) занятие[.!]?$",
        r"^start (tutoring|lesson)[.!]?$",
    ),
    ConversationIntent.REQUEST_NEXT_EXERCISE: (
        r"^(дай|покажи) следующую задачу[.!]?$",
        r"^(give|show) (me )?the next exercise[.!]?$",
    ),
    ConversationIntent.REQUEST_EXERCISE: (
        r"^(дай|покажи) (мне )?задачу(?: на .+)?[.!]?$",
        r"^(give|show) (me )?(an? )?exercise(?: on .+)?[.!]?$",
    ),
    ConversationIntent.SUBMIT_ANSWER: (
        r"^(?:мой ответ|проверь ответ)\s*:\s*(.+)$",
        r"^(?:my answer|check answer)\s*:\s*(.+)$",
    ),
    ConversationIntent.REQUEST_HINT: (
        r"^(дай|покажи) подсказку[.!]?$",
        r"^(give|show) (me )?a hint[.!]?$",
    ),
    ConversationIntent.REQUEST_SOLUTION: (
        r"^покажи решение[.!]?$",
        r"^show (me )?the solution[.!]?$",
    ),
    ConversationIntent.REQUEST_EXPLANATION: (r"^объясни\s+(.+)$", r"^explain\s+(.+)$"),
    ConversationIntent.REQUEST_FACT: (
        r"^(?:какой|назови)\s+(атомный номер|символ|атомный вес)\s+([A-Z][a-z]?)\??$",
        r"^(?:what is|give)\s+(?:the\s+)?(atomic number|symbol|atomic weight)\s+(?:of\s+)?([A-Z][a-z]?)\??$",
    ),
    ConversationIntent.REQUEST_PROGRESS: (
        r"^(покажи мой прогресс|что у меня получается хуже всего)\??$",
        r"^(show my progress|what am i struggling with)\??$",
    ),
    ConversationIntent.CHANGE_LANGUAGE: (
        r"^переключись на английский[.!]?$",
        r"^switch to russian[.!]?$",
    ),
    ConversationIntent.CONFIRM_PENDING_ACTION: (
        r"^(да,?\s*)?(выполни|подтверждаю)( расч[её]т)?[.!]?$",
        r"^(yes,?\s*)?(confirm|execute)( the calculation)?[.!]?$",
    ),
    ConversationIntent.CANCEL_PENDING_ACTION: (
        r"^(отмени|не выполняй)( расч[её]т)?[.!]?$",
        r"^(cancel|do not execute)( the calculation)?[.!]?$",
    ),
    ConversationIntent.PAUSE: (
        r"^(поставь занятие на паузу|пауза)[.!]?$",
        r"^(pause (the )?(lesson|session)|pause)[.!]?$",
    ),
    ConversationIntent.RESUME: (
        r"^(продолжить|продолжи) занятие[.!]?$",
        r"^resume (the )?(lesson|session)[.!]?$",
    ),
    ConversationIntent.END_CONVERSATION: (
        r"^(закончить|закончи) занятие[.!]?$",
        r"^(end|finish) (the )?(lesson|session)[.!]?$",
    ),
}


def parse_intent(text: str, language: str) -> ParsedIntent:
    if (
        language not in {"ru", "en"}
        or not isinstance(text, str)
        or not text.strip()
        or len(text) > MAX_TEXT
    ):
        return _parsed(
            ConversationIntent.CLARIFY, language, {}, ("bounded-input-failure",)
        )
    normalized = " ".join(text.strip().split())
    matches = []
    for intent, patterns in PATTERNS.items():
        match = re.fullmatch(
            patterns[0 if language == "ru" else 1], normalized, re.IGNORECASE
        )
        if match:
            payload = {}
            if intent in {
                ConversationIntent.SUBMIT_ANSWER,
                ConversationIntent.REQUEST_EXPLANATION,
            }:
                payload["text"] = match.group(match.lastindex or 1).strip()
            elif intent is ConversationIntent.REQUEST_FACT:
                label = match.group(1).casefold()
                payload = {
                    "predicate": {
                        "атомный номер": "atomic_number",
                        "символ": "element_symbol",
                        "атомный вес": "conventional_atomic_weight",
                        "atomic number": "atomic_number",
                        "symbol": "element_symbol",
                        "atomic weight": "conventional_atomic_weight",
                    }[label],
                    "symbol": match.group(2),
                }
            elif intent is ConversationIntent.REQUEST_EXERCISE:
                payload["family"] = _exercise_family(normalized)
            matches.append((intent, payload))
    marker_patterns = (
        (
            r"\b(дай|покажи|проверь|объясни|выполни|отмени|переключись|поставь|продолжи|закончи)\b",
            r"\b(give|show|check|explain|confirm|execute|cancel|switch|pause|resume|end|finish)\b",
        )
    )[0 if language == "ru" else 1]
    action_markers = len(re.findall(marker_patterns, normalized, re.IGNORECASE))
    conjunction = bool(re.search(r"\b(и|and|then|сразу)\b", normalized))
    if len(matches) > 1 or (conjunction and action_markers > 0):
        return _parsed(
            ConversationIntent.COMPOSITE_REQUIRED, language, {}, ("multiple-actions",)
        )
    if matches:
        return _parsed(
            matches[0][0], language, matches[0][1], ("exact-controlled-pattern",)
        )
    return _parsed(
        ConversationIntent.CLARIFY,
        language,
        {"candidate_answer": text},
        ("unrecognized-data",),
    )


def _parsed(intent, language, payload, evidence):
    body = {
        "intent": intent,
        "language": language,
        "payload": payload,
        "evidence": evidence,
        "parser_version": CONTROLLED_INTENT_VERSION,
    }
    return ParsedIntent(**body, intent_hash=content_hash(body))


def _exercise_family(text: str) -> str:
    text = text.casefold()
    if any(word in text for word in ("факт", "элемент", "fact", "element")):
        return "FACT_RETRIEVAL"
    if any(word in text for word in ("состав", "composition")):
        return "FORMULA_COMPOSITION"
    if any(word in text for word in ("скоб", "grouped")):
        return "MOLAR_MASS_GROUPED"
    if any(word in text for word in ("массы в моли", "mass to mole", "moles to mass")):
        return "MASS_AMOUNT"
    if any(word in text for word in ("частиц", "сущност", "entit")):
        return "AMOUNT_ENTITIES"
    return "MOLAR_MASS_SIMPLE"
