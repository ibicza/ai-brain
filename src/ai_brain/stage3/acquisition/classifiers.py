from __future__ import annotations

import re

from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    SegmentKind,
    SourceSegment,
)
from ai_brain.stage3.knowledge_ir.records import KnowledgeKind


def classify_segment(
    segment: SourceSegment,
) -> tuple[KnowledgeKind, ExtractionMethod] | None:
    text = segment.canonical_text.strip()
    lower = text.casefold()
    structured = ExtractionMethod.DETERMINISTIC_STRUCTURED
    if lower.startswith("@concept"):
        return KnowledgeKind.CONCEPT, structured
    if lower.startswith("@definition"):
        return KnowledgeKind.DEFINITION, structured
    if lower.startswith("@entity"):
        return KnowledgeKind.ENTITY_TYPE, structured
    if lower.startswith("@relation-type"):
        return KnowledgeKind.RELATION_TYPE, structured
    if lower.startswith("@taxonomy"):
        return KnowledgeKind.TAXONOMY_EDGE, structured
    if lower.startswith("@part-of"):
        return KnowledgeKind.PART_WHOLE_RELATION, structured
    if lower.startswith("@quantity"):
        return KnowledgeKind.QUANTITY_TYPE, structured
    if lower.startswith("@unit"):
        return KnowledgeKind.UNIT_DEFINITION, structured
    if lower.startswith("@equation"):
        return KnowledgeKind.EQUATION_RULE, structured
    if lower.startswith("@condition"):
        return KnowledgeKind.APPLICABILITY_CONDITION, structured
    if lower.startswith("@exception"):
        return KnowledgeKind.EXCEPTION_RULE, structured
    if lower.startswith("@event"):
        return KnowledgeKind.TEMPORAL_RELATION, structured
    if lower.startswith("@spatial"):
        return KnowledgeKind.SPATIAL_RELATION, structured
    if lower.startswith("@causal"):
        return KnowledgeKind.CAUSAL_RULE, structured
    if lower.startswith("@interpretation"):
        return KnowledgeKind.INTERPRETATION, structured
    if lower.startswith("@api"):
        return KnowledgeKind.CLAIM_SCHEMA, structured
    if lower.startswith("@example"):
        return KnowledgeKind.EXAMPLE, structured
    if lower.startswith("@counterexample"):
        return KnowledgeKind.COUNTEREXAMPLE, structured
    if lower.startswith("@test"):
        return KnowledgeKind.TEST_CASE, structured
    if segment.kind is SegmentKind.API_SIGNATURE:
        return KnowledgeKind.CLAIM_SCHEMA, ExtractionMethod.DETERMINISTIC_PATTERN
    if segment.kind is SegmentKind.EQUATION_BLOCK:
        return KnowledgeKind.EQUATION_RULE, ExtractionMethod.DETERMINISTIC_PATTERN
    if re.match(r"^[A-Z][\w -]{1,80}\s+(?:is|means|refers to)\s+.+[.]$", text):
        return KnowledgeKind.DEFINITION, ExtractionMethod.DETERMINISTIC_PATTERN
    return None
