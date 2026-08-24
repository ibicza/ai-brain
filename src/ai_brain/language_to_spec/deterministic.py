"""Transparent rule/template baseline for the controlled command language."""

from __future__ import annotations

import re

from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    ValidationIssue,
    build_family_specification,
    validate_specification,
)

_UNSUPPORTED = re.compile(
    r"\b(copy|swap|sort|multiply|duplicate|скопир|поменяй местами|отсортир|умнож|продублир)",
    re.IGNORECASE,
)
_MOVE = re.compile(
    r"\b(move|transfer|relocate|shift|send|receive|collect|перемест|перенес|перелож|направ|оказаться|собер)",
    re.IGNORECASE,
)
_DROP = re.compile(
    r"\b(clear|remove|drop|discard|empty out|dispose|очист|удал|освобод|убер|устран|опустош)",
    re.IGNORECASE,
)
_NOOP = re.compile(
    r"(leave every register unchanged|make no state change|не изменяй ни один регистр|оставь состояние прежним)",
    re.IGNORECASE,
)
_PRONOUN = re.compile(r"\b(clear it|remove it|очисти его|удали его)\b", re.IGNORECASE)
_UNCLEAR_ORDER = re.compile(r"required order|нужном порядке", re.IGNORECASE)
_OTHER_REGISTER = re.compile(
    r"\bthe other register\b|\bдругой регистр\b", re.IGNORECASE
)
_SAME_DROP_TRANSFER = re.compile(
    r"clear\s+([A-D]).*also transfer all of\s+\1|очисти\s+([A-D]).*одновременно перенеси всё из\s+\2",
    re.IGNORECASE,
)
_IMPOSSIBLE_TERMINATION = re.compile(
    r"leave\s+([A-D])\s+unchanged.*when\s+\1\s+is empty|не изменяй\s+([A-D]).*когда\s+\2\s+опустеет",
    re.IGNORECASE,
)
_DEST_PATTERNS = (
    re.compile(
        r"\b(?:into|to|toward|inside)\s+(?:register\s+)?([A-D])\b", re.IGNORECASE
    ),
    re.compile(r"\bв\s+([A-D])\b", re.IGNORECASE),
    re.compile(r"^\s*([A-D])\s+should\s+receive", re.IGNORECASE),
    re.compile(r"^\s*(?:let|пусть)\s+([A-D])\s+(?:collect|собер)", re.IGNORECASE),
    re.compile(r"^\s*в\s+([A-D])\s+должны", re.IGNORECASE),
)
_PRESERVE_SENTENCE = re.compile(
    r"([^.!;]*(?:unchanged|preserve|intact|do not alter|не изменяй|сохрани|нетронут|не трогай)[^.!;]*)",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    return "ru" if re.search(r"[А-Яа-яЁё]", text) else "en"


def _roles(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\b([A-D])\b", text.upper())))


def _issue(code: ValidationCode, field: str, message: str) -> ValidationIssue:
    return ValidationIssue(code, field, message)


def _negative(
    text: str,
    language: str,
    status: ParseStatus,
    code: ValidationCode,
    field: str,
    message: str,
) -> LanguageProposal:
    return LanguageProposal(
        status=status,
        language=language,
        original_text=text,
        issues=(_issue(code, field, message),),
        confidence=1.0,
        parser_name="deterministic_template_v1",
    )


def _destination(text: str) -> str | None:
    for pattern in _DEST_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return None


def _explicit_preserve(text: str) -> set[str]:
    result: set[str] = set()
    for match in _PRESERVE_SENTENCE.finditer(text):
        result.update(_roles(match.group(1)))
    return result


def parse_controlled_language(
    text: str, *, language: str | None = None
) -> LanguageProposal:
    language = language or detect_language(text)
    normalized = " ".join(text.split())
    roles = _roles(normalized)
    if _UNSUPPORTED.search(normalized):
        return _negative(
            text,
            language,
            ParseStatus.UNSUPPORTED,
            ValidationCode.UNSUPPORTED_OPERATION,
            "operation",
            "The requested operation is outside the frozen Stage-1 grammar",
        )
    if _SAME_DROP_TRANSFER.search(normalized):
        return _negative(
            text,
            language,
            ParseStatus.CONTRADICTORY,
            ValidationCode.DROP_TRANSFER_CONFLICT,
            "drops",
            "The same source is both dropped and transferred",
        )
    if _IMPOSSIBLE_TERMINATION.search(normalized):
        return _negative(
            text,
            language,
            ParseStatus.CONTRADICTORY,
            ValidationCode.IMPOSSIBLE_TERMINATION,
            "terminate_when_empty",
            "A preserved register cannot also be required to become empty",
        )
    if _PRONOUN.search(normalized):
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.AMBIGUOUS_PRONOUN,
            "reference",
            "The controlled grammar cannot resolve the pronoun safely",
        )
    if _UNCLEAR_ORDER.search(normalized):
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.UNCLEAR_ORDER,
            "phase_constraints",
            "Multiple actions are present without an explicit order",
        )
    if _OTHER_REGISTER.search(normalized):
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.MISSING_PRESERVE_BEHAVIOR,
            "preserve",
            "The preserved register is not named",
        )
    if _NOOP.search(normalized):
        spec = build_family_specification(SemanticFamily.NOOP)
        return LanguageProposal(
            ParseStatus.SUPPORTED,
            language,
            text,
            spec,
            SemanticFamily.NOOP,
            confidence=1.0,
            parser_name="deterministic_template_v1",
        )

    has_move = bool(_MOVE.search(normalized))
    has_drop = bool(_DROP.search(normalized))
    destination = _destination(normalized) if has_move else None
    preserve = _explicit_preserve(normalized)

    if has_move and destination is None:
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.MISSING_DESTINATION,
            "outputs",
            "A transfer source is present but no destination is named",
        )

    action_text = normalized.split(".", 1)[0]
    action_roles = list(_roles(action_text))
    if destination in action_roles:
        action_roles.remove(destination)
    action_roles = [role for role in action_roles if role not in preserve]

    if has_move and preserve.intersection(
        action_roles + ([destination] if destination else [])
    ):
        return _negative(
            text,
            language,
            ParseStatus.CONTRADICTORY,
            ValidationCode.PRESERVE_TRANSFER_CONFLICT,
            "preserve",
            "The same register is both modified and preserved",
        )
    if has_drop and has_move:
        ordered = bool(
            re.search(
                r"\b(first|then|after|before|in order|сначала|затем|после|перед|по очереди)\b",
                normalized,
                re.IGNORECASE,
            )
        )
        if not ordered:
            return _negative(
                text,
                language,
                ParseStatus.AMBIGUOUS,
                ValidationCode.UNCLEAR_ORDER,
                "phase_constraints",
                "Drop and transfer actions require explicit order",
            )
        if len(action_roles) < 2:
            return _negative(
                text,
                language,
                ParseStatus.CONTRADICTORY,
                ValidationCode.DROP_TRANSFER_CONFLICT,
                "drops",
                "A register cannot be both dropped and transferred",
            )
        family = SemanticFamily.DROP_THEN_TRANSFER
        sources = tuple(action_roles[:2])
    elif has_drop:
        if not action_roles:
            action_roles = list(roles[:1])
        family = SemanticFamily.CLEAR
        sources = tuple(action_roles[:1])
    elif has_move:
        sources = tuple(action_roles)
        family = {
            1: SemanticFamily.DRAIN,
            2: SemanticFamily.MERGE_TWO,
            3: SemanticFamily.MERGE_THREE,
        }.get(len(sources))
        if family is None:
            return _negative(
                text,
                language,
                ParseStatus.UNSUPPORTED,
                ValidationCode.UNSUPPORTED_OPERATION,
                "inputs",
                "Only one-, two-, and three-source transfers are supported",
            )
    else:
        return _negative(
            text,
            language,
            ParseStatus.UNSUPPORTED,
            ValidationCode.UNSUPPORTED_OPERATION,
            "operation",
            "No controlled operation was recognized",
        )

    try:
        spec = build_family_specification(
            family,
            sources=sources,
            destination=destination,
        )
    except ValueError as exc:
        return _negative(
            text,
            language,
            ParseStatus.CONTRADICTORY,
            ValidationCode.INVALID_SCHEMA,
            "specification",
            str(exc),
        )
    issues = validate_specification(spec)
    if issues:
        return LanguageProposal(
            ParseStatus.CONTRADICTORY,
            language,
            text,
            spec,
            family,
            issues,
            1.0,
            "deterministic_template_v1",
        )
    return LanguageProposal(
        ParseStatus.SUPPORTED,
        language,
        text,
        spec,
        family,
        confidence=1.0,
        parser_name="deterministic_template_v1",
    )
