"""Single-round typed clarification for controlled-language proposals."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage1.models import IssueCode, RuleProposal


@dataclass(frozen=True)
class ClarificationRequest:
    code: IssueCode
    question_ru: str
    question_en: str
    allowed_answers: str


_QUESTIONS = {
    IssueCode.MISSING_DESTINATION: ClarificationRequest(
        IssueCode.MISSING_DESTINATION,
        "Какой регистр A-D является приёмником?",
        "Which A-D register is the destination?",
        "destination=A|B|C|D",
    ),
    IssueCode.MISSING_PRESERVE_BEHAVIOR: ClarificationRequest(
        IssueCode.MISSING_PRESERVE_BEHAVIOR,
        "Какие регистры должны остаться без изменений?",
        "Which registers must remain unchanged?",
        "preserve=A,B or preserve=NONE",
    ),
    IssueCode.MISSING_TERMINATION: ClarificationRequest(
        IssueCode.MISSING_TERMINATION,
        "Какие источники должны опустеть перед остановкой?",
        "Which sources must be empty before stopping?",
        "terminate=A,B or terminate=IMMEDIATE",
    ),
    IssueCode.UNCLEAR_ORDER: ClarificationRequest(
        IssueCode.UNCLEAR_ORDER,
        "Подтвердите порядок фаз через запятую.",
        "Confirm the phase order as a comma-separated source list.",
        "order=A,B",
    ),
    IssueCode.AMBIGUOUS_PRONOUN: ClarificationRequest(
        IssueCode.AMBIGUOUS_PRONOUN,
        "Какой регистр обозначает местоимение?",
        "Which register does the pronoun refer to?",
        "reference=A|B|C|D",
    ),
}


def clarification_for(proposal: RuleProposal) -> ClarificationRequest | None:
    if not proposal.issues:
        return None
    return _QUESTIONS.get(proposal.issues[0].code)
