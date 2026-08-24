"""One bounded, field-targeted clarification round."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    ValidationIssue,
    build_family_specification,
)


@dataclass(frozen=True)
class ClarificationRequest:
    code: ValidationCode
    field: str
    language: str
    question: str


_QUESTIONS = {
    "en": {
        ValidationCode.MISSING_DESTINATION: "Where should the items from {source} be moved?",
        ValidationCode.MISSING_PRESERVE_BEHAVIOR: "Which register should remain unchanged?",
        ValidationCode.UNCLEAR_ORDER: "Should {first} be cleared before {second} is moved?",
        ValidationCode.AMBIGUOUS_PRONOUN: "Which named register does the reference mean?",
    },
    "ru": {
        ValidationCode.MISSING_DESTINATION: "Куда нужно переместить элементы из {source}?",
        ValidationCode.MISSING_PRESERVE_BEHAVIOR: "Какой регистр нужно сохранить без изменений?",
        ValidationCode.UNCLEAR_ORDER: "Сначала очистить {first}, а затем выполнить перенос {second}?",
        ValidationCode.AMBIGUOUS_PRONOUN: "Какой именно регистр обозначает это местоимение?",
    },
}


def clarification_for(proposal: LanguageProposal) -> ClarificationRequest | None:
    if proposal.status != ParseStatus.AMBIGUOUS or not proposal.issues:
        return None
    issue = proposal.issues[0]
    template = _QUESTIONS.get(proposal.language, {}).get(issue.code)
    if template is None:
        return None
    roles = re.findall(r"\b([A-D])\b", proposal.original_text.upper())
    values = {
        "source": roles[0] if roles else "A",
        "first": roles[0] if roles else "A",
        "second": roles[1] if len(roles) > 1 else "B",
    }
    return ClarificationRequest(
        issue.code, issue.field, proposal.language, template.format(**values)
    )


def resolve_one_round(proposal: LanguageProposal, answer: str) -> LanguageProposal:
    request = clarification_for(proposal)
    if request is None:
        return proposal
    answer_roles = re.findall(r"\b([A-D])\b", answer.upper())
    original_roles = tuple(
        dict.fromkeys(re.findall(r"\b([A-D])\b", proposal.original_text.upper()))
    )
    if (
        request.code == ValidationCode.MISSING_DESTINATION
        and answer_roles
        and original_roles
    ):
        destination = answer_roles[0]
        source = original_roles[0]
        if destination != source:
            spec = build_family_specification(
                SemanticFamily.DRAIN,
                sources=(source,),
                destination=destination,
            )
            return LanguageProposal(
                ParseStatus.SUPPORTED,
                proposal.language,
                proposal.original_text,
                spec,
                SemanticFamily.DRAIN,
                confidence=1.0,
                parser_name=proposal.parser_name,
                provenance=(("clarification", answer),),
            )
    if (
        request.code
        in {
            ValidationCode.MISSING_PRESERVE_BEHAVIOR,
            ValidationCode.AMBIGUOUS_PRONOUN,
        }
        and len(original_roles) >= 2
        and answer_roles
    ):
        source, destination = original_roles[:2]
        if answer_roles[0] not in {source, destination}:
            spec = build_family_specification(
                SemanticFamily.DRAIN,
                sources=(source,),
                destination=destination,
            )
            return LanguageProposal(
                ParseStatus.SUPPORTED,
                proposal.language,
                proposal.original_text,
                spec,
                SemanticFamily.DRAIN,
                confidence=1.0,
                parser_name=proposal.parser_name,
                provenance=(("clarification", answer),),
            )
    if request.code == ValidationCode.UNCLEAR_ORDER and len(original_roles) >= 3:
        normalized = answer.casefold().strip()
        if normalized in {"yes", "yes.", "да", "да."}:
            spec = build_family_specification(
                SemanticFamily.DROP_THEN_TRANSFER,
                sources=(original_roles[0], original_roles[1]),
                destination=original_roles[2],
            )
            return LanguageProposal(
                ParseStatus.SUPPORTED,
                proposal.language,
                proposal.original_text,
                spec,
                SemanticFamily.DROP_THEN_TRANSFER,
                confidence=1.0,
                parser_name=proposal.parser_name,
                provenance=(("clarification", answer),),
            )
    return LanguageProposal(
        ParseStatus.AMBIGUOUS,
        proposal.language,
        proposal.original_text,
        proposal.specification,
        proposal.semantic_family,
        (
            ValidationIssue(
                request.code,
                request.field,
                "One clarification round did not resolve the controlled field",
            ),
        ),
        0.0,
        proposal.parser_name,
        (("clarification", answer),),
    )
