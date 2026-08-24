"""Honest train-lexicon and extended production parsers for M-23.1."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Literal

from ai_brain.language_to_spec.fair_data import HOLDOUT_LEXICON, TRAIN_LEXICON
from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    ValidationIssue,
    build_family_specification,
    validate_specification,
)

LexiconMode = Literal["train", "extended"]


def _issue(code: ValidationCode, field: str, message: str) -> ValidationIssue:
    return ValidationIssue(code, field, message)


def _negative(
    text: str,
    language: str,
    status: ParseStatus,
    code: ValidationCode,
    field: str,
    *,
    mode: LexiconMode,
) -> LanguageProposal:
    return LanguageProposal(
        status,
        language,
        text,
        issues=(_issue(code, field, "Controlled deterministic parser decision"),),
        confidence=1.0,
        parser_name=f"deterministic_{mode}_lexicon_v2",
    )


def _language(text: str) -> str:
    return "ru" if re.search(r"[А-Яа-яЁё]", text) else "en"


def _lexemes(language: str, concept: str, mode: LexiconMode) -> tuple[str, ...]:
    values = list(TRAIN_LEXICON[language][concept])
    if mode == "extended":
        values.extend(HOLDOUT_LEXICON[language][concept])
    if concept == "preserve":
        values.extend(("do not modify", "не меняй"))
    return tuple(values)


def _contains(text: str, values: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text, re.IGNORECASE) is not None
        for value in values
    )


def _roles(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\b([A-D])\b", text.upper())))


def _operation_clause(
    text: str, language: str, mode: LexiconMode
) -> tuple[str, bool, bool]:
    move_lexemes = _lexemes(language, "move", mode)
    drop_lexemes = _lexemes(language, "drop", mode)
    clauses = re.split(r"[.!;]+", text)
    matching = [
        clause
        for clause in clauses
        if _contains(clause, move_lexemes) or _contains(clause, drop_lexemes)
    ]
    if not matching:
        return "", False, False
    joined = " ".join(matching[:2])
    return (
        joined,
        _contains(joined, move_lexemes),
        _contains(joined, drop_lexemes),
    )


def _preserve_roles(
    text: str, language: str, mode: LexiconMode
) -> tuple[bool, set[str]]:
    empty_marker = (
        "no register is required to remain unchanged"
        if language == "en"
        else "нет регистра, который требуется сохранить без изменений"
    )
    if empty_marker in text.casefold():
        return True, set()
    patterns = {
        "en": [
            r"\bleave\b.*\bunchanged\b",
            r"\bpreserve\b",
            r"\bdo not modify\b",
        ],
        "ru": [
            r"\bне изменяй\b",
            r"\bсохрани\b.*\bбез изменений\b",
            r"\bне меняй\b",
        ],
    }
    if mode == "extended":
        patterns["en"].extend(
            (r"\bretain\b.*\buntouched\b", r"\bmaintain\b.*\bintact\b")
        )
        patterns["ru"].extend(
            (
                r"\bсбереги\b.*\bкак есть\b",
                r"\bподдерживай\b.*\bбез изменений\b",
            )
        )
    clauses = re.split(r"[.!;]+", text)
    for clause in clauses:
        if any(
            re.search(pattern, clause, re.IGNORECASE) for pattern in patterns[language]
        ):
            return True, set(_roles(clause))
    return False, set()


def _termination_roles(
    text: str, language: str, mode: LexiconMode
) -> tuple[bool, tuple[str, ...]]:
    immediate = (
        "no register must first become empty"
        if language == "en"
        else "ни один регистр не должен сначала опустеть"
    )
    clauses = re.split(r"[.!;]+", text)
    for clause in clauses:
        if immediate in clause.casefold():
            return True, ()
        if _contains(clause, _lexemes(language, "stop", mode)):
            return True, _roles(clause)
    return False, ()


def parse_fair_controlled_language(
    text: str,
    *,
    language: str | None = None,
    lexicon_mode: LexiconMode = "train",
) -> LanguageProposal:
    language = language or _language(text)
    folded = text.casefold()
    if re.search(r"\b(copy|скопируй)\b", folded):
        return _negative(
            text,
            language,
            ParseStatus.UNSUPPORTED,
            ValidationCode.UNSUPPORTED_OPERATION,
            "operation",
            mode=lexicon_mode,
        )
    if re.search(
        r"move every item from ([A-D]).*leave \1 unchanged", text, re.IGNORECASE
    ) or re.search(
        r"перемести все элементы из ([A-D]).*\1 не изменяй", text, re.IGNORECASE
    ):
        return _negative(
            text,
            language,
            ParseStatus.CONTRADICTORY,
            ValidationCode.PRESERVE_TRANSFER_CONFLICT,
            "preserve",
            mode=lexicon_mode,
        )
    if re.search(
        r"clear ([A-D]).*transfer every item from \1", text, re.IGNORECASE
    ) or re.search(r"очисти ([A-D]).*перенеси все элементы из \1", text, re.IGNORECASE):
        return _negative(
            text,
            language,
            ParseStatus.CONTRADICTORY,
            ValidationCode.DROP_TRANSFER_CONFLICT,
            "drops",
            mode=lexicon_mode,
        )
    if re.search(
        r"leave ([A-D]) unchanged.*when \1 is empty", text, re.IGNORECASE
    ) or re.search(r"не изменяй ([A-D]).*когда \1 опустеет", text, re.IGNORECASE):
        return _negative(
            text,
            language,
            ParseStatus.CONTRADICTORY,
            ValidationCode.IMPOSSIBLE_TERMINATION,
            "terminate_when_empty",
            mode=lexicon_mode,
        )
    if "leave it unchanged" in folded or "его тоже не изменяй" in folded:
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.AMBIGUOUS_PRONOUN,
            "reference",
            mode=lexicon_mode,
        )
    operation, has_move, has_drop = _operation_clause(text, language, lexicon_mode)
    noop = (
        "leave all registers unchanged" in folded
        or "оставь все регистры без изменений" in folded
    )
    if noop:
        spec = build_family_specification(SemanticFamily.NOOP)
        return LanguageProposal(
            ParseStatus.SUPPORTED,
            language,
            text,
            spec,
            SemanticFamily.NOOP,
            confidence=1.0,
            parser_name=f"deterministic_{lexicon_mode}_lexicon_v2",
        )
    if not operation:
        return _negative(
            text,
            language,
            ParseStatus.UNSUPPORTED,
            ValidationCode.UNSUPPORTED_OPERATION,
            "operation",
            mode=lexicon_mode,
        )
    operation_roles = list(_roles(operation))
    if has_move and len(operation_roles) < 2:
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.MISSING_DESTINATION,
            "outputs",
            mode=lexicon_mode,
        )
    explicit_preserve, preserve = _preserve_roles(text, language, lexicon_mode)
    if not explicit_preserve:
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.MISSING_PRESERVE_BEHAVIOR,
            "preserve",
            mode=lexicon_mode,
        )
    explicit_termination, termination = _termination_roles(text, language, lexicon_mode)
    if not explicit_termination:
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.MISSING_TERMINATION_CONDITION,
            "terminate_when_empty",
            mode=lexicon_mode,
        )
    if (
        has_drop
        and has_move
        and not re.search(
            r"\b(first|then|before|afterward|phase one|сначала|затем|до того|первой фазе|после этого)\b",
            operation,
            re.IGNORECASE,
        )
    ):
        return _negative(
            text,
            language,
            ParseStatus.AMBIGUOUS,
            ValidationCode.UNCLEAR_ORDER,
            "phase_constraints",
            mode=lexicon_mode,
        )
    try:
        if has_drop and has_move:
            family = SemanticFamily.DROP_THEN_TRANSFER
            sources = tuple(operation_roles[:2])
            destination = operation_roles[-1]
        elif has_drop:
            family = SemanticFamily.CLEAR
            sources = (operation_roles[0],)
            destination = None
        else:
            destination = operation_roles[-1]
            sources = tuple(operation_roles[:-1])
            family = {
                1: SemanticFamily.DRAIN,
                2: SemanticFamily.MERGE_TWO,
                3: SemanticFamily.MERGE_THREE,
            }[len(sources)]
        base = build_family_specification(
            family, sources=sources, destination=destination
        )
        specification = replace(
            base,
            preserve=tuple(sorted(preserve)),
            terminate_when_empty=termination,
        )
        issues = validate_specification(specification)
        if issues:
            raise ValueError(str(issues[0].code))
    except (KeyError, ValueError, IndexError) as exc:
        return LanguageProposal(
            ParseStatus.CONTRADICTORY,
            language,
            text,
            issues=(_issue(ValidationCode.INVALID_SCHEMA, "specification", str(exc)),),
            confidence=1.0,
            parser_name=f"deterministic_{lexicon_mode}_lexicon_v2",
        )
    return LanguageProposal(
        ParseStatus.SUPPORTED,
        language,
        text,
        specification,
        family,
        confidence=1.0,
        parser_name=f"deterministic_{lexicon_mode}_lexicon_v2",
    )


def frozen_lexicon_items() -> set[str]:
    return {
        item.casefold()
        for language in TRAIN_LEXICON.values()
        for concept in language.values()
        for item in concept
    }


def holdout_lexicon_items() -> set[str]:
    return {
        item.casefold()
        for language in HOLDOUT_LEXICON.values()
        for concept in language.values()
        for item in concept
    }
