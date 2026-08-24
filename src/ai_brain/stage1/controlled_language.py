"""Strict deterministic RU/EN controlled-language frontend."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.models import (
    IssueCode,
    ProposalIssue,
    ProposalStatus,
    SemanticFamily,
)
from ai_brain.stage1.specifications import build_family_specification

PARSER_NAME = "stage1_deterministic_controlled_language"

LEXICON = {
    "en": {
        "move": ("move", "transfer", "convey", "channel"),
        "drop": ("clear", "remove", "purge", "expunge"),
        "preserve": (
            "leave unchanged",
            "preserve",
            "do not modify",
            "retain untouched",
            "maintain intact",
        ),
        "stop": ("stop", "finish", "cease execution", "conclude"),
    },
    "ru": {
        "move": ("перемести", "перенеси", "перебрось", "переправь"),
        "drop": ("очисти", "удали", "ликвидируй", "избавься от содержимого"),
        "preserve": (
            "не изменяй",
            "сохрани без изменений",
            "не меняй",
            "сбереги как есть",
            "поддерживай без изменений",
        ),
        "stop": (
            "остановись",
            "заверши работу",
            "прерви выполнение",
            "закончи операцию",
        ),
    },
}


@dataclass(frozen=True)
class ParseOutcome:
    status: ProposalStatus
    language: str
    specification: ProgramSpecification | None
    family: SemanticFamily | None
    issues: tuple[ProposalIssue, ...] = ()
    partial_actions: tuple[tuple[str, str, str | None], ...] = ()


def detect_language(text: str) -> str:
    return "ru" if re.search(r"[А-Яа-яЁё]", text) else "en"


def parse_controlled_language(text: str, language: str | None = None) -> ParseOutcome:
    lang = language or detect_language(text)
    if lang not in LEXICON:
        return _out(
            ProposalStatus.UNSUPPORTED,
            lang,
            IssueCode.UNSUPPORTED_OPERATION,
            "language",
        )
    folded = _normalize(text)
    if re.search(r"\b(copy|duplicate|скопируй|дублируй)\b", folded):
        return _out(
            ProposalStatus.UNSUPPORTED,
            lang,
            IssueCode.UNSUPPORTED_OPERATION,
            "operation",
        )
    if _contradictory(folded, lang):
        return _out(
            ProposalStatus.CONTRADICTORY, lang, IssueCode.CONTRADICTION, "specification"
        )
    if (
        re.search(r"\b(it|this|that|его|её|это)\b", folded)
        and "reference=" not in folded
    ):
        return _out(
            ProposalStatus.CLARIFICATION_REQUIRED,
            lang,
            IssueCode.AMBIGUOUS_PRONOUN,
            "reference",
        )

    clauses = [item.strip() for item in re.split(r"[.;!]+", folded) if item.strip()]
    operation = [
        item
        for item in clauses
        if _contains(item, LEXICON[lang]["move"])
        or _contains(item, LEXICON[lang]["drop"])
    ]
    noop = (
        "leave all registers unchanged" in folded
        or "оставь все регистры без изменений" in folded
    )
    preserve_explicit, preserved = _preserve(folded, lang)
    termination_explicit, terminated = _termination(folded, lang)
    if noop:
        if not termination_explicit:
            return _out(
                ProposalStatus.CLARIFICATION_REQUIRED,
                lang,
                IssueCode.MISSING_TERMINATION,
                "terminate_when_empty",
            )
        return ParseOutcome(
            ProposalStatus.SUPPORTED_FOR_REVIEW,
            lang,
            build_family_specification(SemanticFamily.NOOP),
            SemanticFamily.NOOP,
        )
    if not operation:
        return _out(
            ProposalStatus.UNSUPPORTED,
            lang,
            IssueCode.UNSUPPORTED_OPERATION,
            "operation",
        )
    operation_text = " ".join(operation[:2])
    has_move = _contains(operation_text, LEXICON[lang]["move"])
    has_drop = _contains(operation_text, LEXICON[lang]["drop"])
    roles = _roles(operation_text)
    destination_answer = _answer_roles(folded, "destination")
    if has_move and len(roles) < 2 and destination_answer:
        roles = (*roles, destination_answer[0])
    partial = _partial_actions(roles, has_move=has_move, has_drop=has_drop)
    if has_move and len(roles) < 2:
        return _out(
            ProposalStatus.CLARIFICATION_REQUIRED,
            lang,
            IssueCode.MISSING_DESTINATION,
            "destination",
            partial,
        )
    if not preserve_explicit:
        return _out(
            ProposalStatus.CLARIFICATION_REQUIRED,
            lang,
            IssueCode.MISSING_PRESERVE_BEHAVIOR,
            "preserve",
            partial,
        )
    if not termination_explicit:
        return _out(
            ProposalStatus.CLARIFICATION_REQUIRED,
            lang,
            IssueCode.MISSING_TERMINATION,
            "terminate_when_empty",
            partial,
        )
    if (
        has_drop
        and has_move
        and "order=" not in folded
        and not re.search(
            r"\b(first|then|before|afterward|сначала|затем|после этого|до того)\b",
            operation_text,
        )
    ):
        return _out(
            ProposalStatus.CLARIFICATION_REQUIRED,
            lang,
            IssueCode.UNCLEAR_ORDER,
            "phase_constraints",
            partial,
        )
    order_answer = _answer_roles(folded, "order")
    if has_drop and has_move and order_answer and order_answer != roles[:2]:
        return _out(
            ProposalStatus.CONTRADICTORY,
            lang,
            IssueCode.CONTRADICTION,
            "phase_constraints",
            partial,
        )
    try:
        family, sources, destination = _family_roles(roles, has_move, has_drop)
        specification = build_family_specification(
            family,
            sources=sources,
            destination=destination,
            preserve=preserved,
        )
    except (KeyError, ValueError, IndexError):
        return _out(
            ProposalStatus.CONTRADICTORY, lang, IssueCode.CONTRADICTION, "specification"
        )
    if set(terminated) != set(sources):
        return _out(
            ProposalStatus.CONTRADICTORY, lang, IssueCode.CONTRADICTION, "termination"
        )
    return ParseOutcome(
        ProposalStatus.SUPPORTED_FOR_REVIEW,
        lang,
        specification,
        family,
        partial_actions=partial,
    )


def language_help(language: str) -> str:
    if language == "ru":
        return (
            "Укажите действие, источники A-D, приёмник, неизменяемые регистры, "
            "условие остановки и порядок фаз. Пример: Перенеси все элементы из A и B "
            "в C; D не изменяй; остановись, когда A и B опустеют."
        )
    return (
        "State the operation, A-D sources, destination, preserved registers, termination, "
        "and phase order. Example: Move every item from A and B into C; leave D unchanged; "
        "stop when A and B are empty."
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _contains(text: str, values: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text) for value in values)


def _roles(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\b([A-D])\b", text.upper())))


def _preserve(text: str, language: str) -> tuple[bool, tuple[str, ...]]:
    if "preserve=none" in text:
        return True, ()
    answer = _answer_roles(text, "preserve")
    if answer:
        return True, answer
    none_markers = (
        ("no register is required to remain unchanged",)
        if language == "en"
        else ("нет регистра, который требуется сохранить без изменений",)
    )
    if any(marker in text for marker in none_markers):
        return True, ()
    patterns = {
        "en": (
            r"\bleave\b.*\bunchanged\b",
            r"\bpreserve\b",
            r"\bdo not modify\b",
            r"\bretain\b.*\buntouched\b",
            r"\bmaintain\b.*\bintact\b",
        ),
        "ru": (
            r"\bне изменяй\b",
            r"\bсохрани\b.*\bбез изменений\b",
            r"\bне меняй\b",
            r"\bсбереги\b.*\bкак есть\b",
            r"\bподдерживай\b.*\bбез изменений\b",
        ),
    }
    for clause in re.split(r"[.;!]+", text):
        if any(re.search(pattern, clause) for pattern in patterns[language]):
            roles = _roles(clause)
            if not roles:
                roles = _answer_roles(text, "reference")
            return True, roles
    return False, ()


def _termination(text: str, language: str) -> tuple[bool, tuple[str, ...]]:
    if "terminate=immediate" in text:
        return True, ()
    answer = _answer_roles(text, "terminate")
    if answer:
        return True, answer
    immediate = (
        "stop immediately" in text
        or "finish immediately" in text
        or "сразу остановись" in text
        or "немедленно заверши" in text
    )
    if immediate:
        return True, ()
    for clause in re.split(r"[.;!]+", text):
        if _contains(clause, LEXICON[language]["stop"]):
            return True, _roles(clause)
    return False, ()


def _family_roles(
    roles: tuple[str, ...], has_move: bool, has_drop: bool
) -> tuple[SemanticFamily, tuple[str, ...], str | None]:
    if has_drop and has_move:
        return SemanticFamily.DROP_THEN_TRANSFER, roles[:2], roles[-1]
    if has_drop:
        return SemanticFamily.CLEAR, (roles[0],), None
    sources, destination = roles[:-1], roles[-1]
    family = {
        1: SemanticFamily.DRAIN,
        2: SemanticFamily.MERGE_TWO,
        3: SemanticFamily.MERGE_THREE,
    }[len(sources)]
    return family, sources, destination


def _partial_actions(
    roles: tuple[str, ...], *, has_move: bool, has_drop: bool
) -> tuple[tuple[str, str, str | None], ...]:
    if has_drop and has_move and len(roles) >= 2:
        return (("DROP_ONE", roles[0], None), ("MOVE_ONE", roles[1], roles[-1]))
    if has_drop and roles:
        return (("DROP_ONE", roles[0], None),)
    if has_move and roles:
        destination = roles[-1] if len(roles) > 1 else None
        return tuple(("MOVE_ONE", role, destination) for role in roles[:-1] or roles)
    return ()


def _contradictory(text: str, language: str) -> bool:
    for role in "ABCD":
        source = role.casefold()
        if language == "en":
            if re.search(
                rf"(?:move|transfer)[^.;]*\b{source}\b[^.;]*(?:leave|preserve)[^.;]*\b{source}\b",
                text,
            ):
                return True
        elif re.search(
            rf"(?:перемести|перенеси)[^.;]*\b{source}\b[^.;]*(?:не изменяй|сохрани)[^.;]*\b{source}\b",
            text,
        ):
            return True
    return False


def _out(
    status: ProposalStatus,
    language: str,
    code: IssueCode,
    field: str,
    partial: tuple[tuple[str, str, str | None], ...] = (),
) -> ParseOutcome:
    return ParseOutcome(
        status,
        language,
        None,
        None,
        (ProposalIssue(code, field, "Controlled deterministic parser decision"),),
        partial,
    )


def _answer_roles(text: str, key: str) -> tuple[str, ...]:
    match = re.search(rf"\b{key}=([a-d](?:\s*,\s*[a-d])*)\b", text, re.IGNORECASE)
    return _roles(match.group(1)) if match else ()
