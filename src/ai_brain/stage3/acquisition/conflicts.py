from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.models import ConflictArtifact, KnowledgeProposal
from ai_brain.stage3.knowledge_ir.records import (
    DefinitionContent,
    InterpretationContent,
    UnitDefinitionContent,
)


def detect_conflicts(
    proposals: tuple[KnowledgeProposal, ...],
) -> tuple[ConflictArtifact, ...]:
    result = []
    for index, left in enumerate(proposals):
        for right in proposals[index + 1 :]:
            kind, field = _conflict(left, right)
            if kind is None:
                continue
            proposal_ids = tuple(sorted((left.proposal_id, right.proposal_id)))
            segment_ids = tuple(sorted({*left.segment_ids, *right.segment_ids}))
            body = {
                "conflict_id": "",
                "proposal_ids": proposal_ids,
                "source_segment_ids": segment_ids,
                "conflict_kind": kind,
                "exact_field": field,
            }
            body["conflict_id"] = f"conflict.{content_hash(body)[:32]}"
            result.append(ConflictArtifact(**body, conflict_hash=content_hash(body)))
    unique = {item.conflict_hash: item for item in result}
    return tuple(unique[key] for key in sorted(unique))


def _conflict(left: KnowledgeProposal, right: KnowledgeProposal):
    if left.proposed_kind != right.proposed_kind:
        return None, None
    if asdict(left.proposed_content) == asdict(right.proposed_content):
        return "DUPLICATE_STATEMENT", "proposed_content"
    a, b = left.proposed_content, right.proposed_content
    if (
        isinstance(a, DefinitionContent)
        and isinstance(b, DefinitionContent)
        and a.term_id == b.term_id
    ):
        return "INCOMPATIBLE_DEFINITION", "proposed_content.definition_en"
    if (
        isinstance(a, UnitDefinitionContent)
        and isinstance(b, UnitDefinitionContent)
        and a.unit.unit_id == b.unit.unit_id
        and a.unit.dimension != b.unit.dimension
    ):
        return "UNIT_CONFLICT", "proposed_content.unit.dimension"
    if (
        isinstance(a, InterpretationContent)
        and isinstance(b, InterpretationContent)
        and set(a.supported_record_ids) & set(b.supported_record_ids)
        and a.claim_text != b.claim_text
    ):
        return "DIFFERING_INTERPRETATION", "proposed_content.claim_text"
    return None, None
