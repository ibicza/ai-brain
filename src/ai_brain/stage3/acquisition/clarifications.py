from __future__ import annotations

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.models import (
    ClarificationKind,
    ClarificationQuestion,
    KnowledgeProposal,
)

_KINDS = {
    "content.variables": ClarificationKind.UNDECLARED_VARIABLE,
    "content.applicability.preconditions": ClarificationKind.MISSING_APPLICABILITY,
    "content.quantity_type.canonical_unit": ClarificationKind.MISSING_UNIT,
    "content.symbol": ClarificationKind.AMBIGUOUS_SYMBOL,
    "proposed_epistemic_character": ClarificationKind.UNCERTAIN_EPISTEMIC,
    "content.preconditions": ClarificationKind.UNKNOWN_EXCEPTION_SCOPE,
    "content.postconditions": ClarificationKind.UNKNOWN_EXCEPTION_SCOPE,
    "proposed_capabilities": ClarificationKind.UNSUPPORTED_CAPABILITY,
}


def generate_clarifications(
    proposals: tuple[KnowledgeProposal, ...],
) -> tuple[ClarificationQuestion, ...]:
    result = []
    for proposal in proposals:
        for field in proposal.ambiguity_fields:
            kind = _KINDS.get(field, ClarificationKind.UNCLEAR_ENTITY)
            body = {
                "clarification_id": "",
                "proposal_id": proposal.proposal_id,
                "kind": kind,
                "exact_field": field,
                "question": f"Provide one exact reviewed value for {field}.",
                "source_segment_ids": proposal.segment_ids,
            }
            body["clarification_id"] = f"clarification.{content_hash(body)[:32]}"
            result.append(
                ClarificationQuestion(**body, clarification_hash=content_hash(body))
            )
    return tuple(result)
