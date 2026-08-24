"""Raw-text clarification pipeline with preserved partial semantics."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ai_brain.language_to_spec.clarification import (
    ClarificationRequest,
    clarification_for,
)
from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    ValidationIssue,
    build_family_specification,
)


@dataclass(frozen=True)
class PartialInterpretation:
    actions: tuple[tuple[str, str, str | None], ...]
    preserve: tuple[str, ...] | None
    termination: tuple[str, ...] | None
    candidate_referents: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClarificationState:
    proposal: LanguageProposal
    partial: PartialInterpretation
    question: ClarificationRequest | None


Parser = Callable[[str, str], LanguageProposal]


def _roles(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\b([A-D])\b", text.upper())))


def partial_interpretation_from_raw(
    text: str, code: ValidationCode
) -> PartialInterpretation:
    roles = _roles(text)
    if code == ValidationCode.MISSING_DESTINATION and roles:
        preserve = tuple(roles[1:])
        return PartialInterpretation(
            (("MOVE_ONE", roles[0], None),), preserve, (roles[0],)
        )
    if code == ValidationCode.UNCLEAR_ORDER and len(roles) >= 4:
        return PartialInterpretation(
            (("DROP_ONE", roles[0], None), ("MOVE_ONE", roles[1], roles[2])),
            (roles[3],),
            (roles[0], roles[1]),
        )
    if code == ValidationCode.MISSING_PRESERVE_BEHAVIOR and len(roles) >= 2:
        return PartialInterpretation(
            (("MOVE_ONE", roles[0], roles[1]),), None, (roles[0],)
        )
    if code == ValidationCode.AMBIGUOUS_PRONOUN and len(roles) >= 3:
        remaining = tuple(
            variable for variable in ("A", "B", "C", "D") if variable not in roles[:3]
        )
        candidates = tuple(dict.fromkeys((*roles[2:], *remaining)))
        return PartialInterpretation(
            (("MOVE_ONE", roles[0], roles[1]),),
            (roles[2],),
            (roles[0],),
            candidates,
        )
    return PartialInterpretation((), None, None)


def clarification_from_raw(
    text: str, language: str, parser: Parser
) -> ClarificationState:
    proposal = parser(text, language)
    if proposal.status != ParseStatus.AMBIGUOUS or not proposal.issues:
        return ClarificationState(proposal, PartialInterpretation((), None, None), None)
    code = proposal.issues[0].code
    partial = partial_interpretation_from_raw(text, code)
    return ClarificationState(proposal, partial, clarification_for(proposal))


def _unresolved(state: ClarificationState, answer: str) -> LanguageProposal:
    code = (
        state.proposal.issues[0].code
        if state.proposal.issues
        else ValidationCode.INVALID_SCHEMA
    )
    return LanguageProposal(
        ParseStatus.AMBIGUOUS,
        state.proposal.language,
        state.proposal.original_text,
        issues=(
            ValidationIssue(
                code,
                "clarification",
                "The bounded clarification answer did not complete the partial interpretation",
            ),
        ),
        confidence=0.0,
        parser_name=state.proposal.parser_name,
        provenance=(("clarification", answer),),
    )


def resolve_clarification_state(
    state: ClarificationState, answer: str
) -> LanguageProposal:
    if state.question is None or not state.proposal.issues:
        return state.proposal
    code = state.proposal.issues[0].code
    answer_roles = _roles(answer)
    actions = state.partial.actions
    try:
        if code == ValidationCode.MISSING_DESTINATION and actions and answer_roles:
            source = actions[0][1]
            destination = answer_roles[0]
            if source == destination:
                return _unresolved(state, answer)
            specification = build_family_specification(
                SemanticFamily.DRAIN, sources=(source,), destination=destination
            )
            family = SemanticFamily.DRAIN
        elif code == ValidationCode.UNCLEAR_ORDER and len(actions) == 2:
            normalized = answer.casefold().strip().rstrip(".")
            if normalized not in {"yes", "да"}:
                return _unresolved(state, answer)
            drop, transfer = actions
            specification = build_family_specification(
                SemanticFamily.DROP_THEN_TRANSFER,
                sources=(drop[1], transfer[1]),
                destination=transfer[2],
            )
            family = SemanticFamily.DROP_THEN_TRANSFER
        elif (
            code
            in {
                ValidationCode.MISSING_PRESERVE_BEHAVIOR,
                ValidationCode.AMBIGUOUS_PRONOUN,
            }
            and actions
        ):
            source, destination = actions[0][1:]
            requested = set(answer_roles)
            if code == ValidationCode.AMBIGUOUS_PRONOUN:
                requested.update(state.partial.preserve or ())
            specification = build_family_specification(
                SemanticFamily.DRAIN,
                sources=(source,),
                destination=destination,
            )
            if requested != set(specification.preserve):
                return _unresolved(state, answer)
            family = SemanticFamily.DRAIN
        else:
            return _unresolved(state, answer)
    except (ValueError, IndexError):
        return _unresolved(state, answer)
    return LanguageProposal(
        ParseStatus.SUPPORTED,
        state.proposal.language,
        state.proposal.original_text,
        specification,
        family,
        confidence=1.0,
        parser_name=state.proposal.parser_name,
        provenance=(
            ("partial_actions", repr(state.partial.actions)),
            ("clarification", answer),
        ),
    )
