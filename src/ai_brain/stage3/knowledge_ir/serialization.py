"""Canonical JSON serialization for the immutable IR."""

from __future__ import annotations

import json
from dataclasses import asdict

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.knowledge_ir.records import *
from ai_brain.stage3.knowledge_ir.validation import validate_record


def dump_record(record: KnowledgeRecord) -> str:
    validate_record(record)
    return canonical_json(asdict(record)) + "\n"


def load_record(text: str) -> KnowledgeRecord:
    row = json.loads(text, object_pairs_hook=_strict_object)
    content = _content_from_dict(KnowledgeKind(row["kind"]), row["content"])
    result = KnowledgeRecord(
        knowledge_id=row["knowledge_id"],
        domain_id=row["domain_id"],
        kind=KnowledgeKind(row["kind"]),
        schema_version=row["schema_version"],
        epistemic_character=EpistemicCharacter(row["epistemic_character"]),
        provenance_refs=tuple(row["provenance_refs"]),
        dependencies=tuple(row["dependencies"]),
        applicability_refs=tuple(row["applicability_refs"]),
        required_capability_ids=tuple(row["required_capability_ids"]),
        created_at=row["created_at"],
        content=content,
        content_hash=row["content_hash"],
    )
    validate_record(result)
    return result


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in knowledge record")
        result[key] = value
    return result


def _expression(row: dict) -> Expression:
    return Expression(
        ExpressionKind(row["kind"]),
        row.get("value"),
        tuple(_expression(x) for x in row.get("children", ())),
        row.get("capability_id"),
    )


def _applicability(row: dict) -> Applicability:
    return Applicability(
        **{k: tuple(v) if isinstance(v, list) else v for k, v in row.items()}
    )


def _content_from_dict(kind: KnowledgeKind, row: dict) -> KnowledgeContent:
    if kind in {
        KnowledgeKind.EQUATION_RULE,
        KnowledgeKind.CONSTRAINT_RULE,
        KnowledgeKind.ALGORITHM,
        KnowledgeKind.STATE_TRANSITION,
        KnowledgeKind.CAUSAL_RULE,
        KnowledgeKind.DEPENDENCY_RULE,
    }:
        return RuleContent(
            _expression(row["expression"]),
            tuple(VariableBinding(**item) for item in row["variables"]),
            _applicability(row["applicability"]),
            tuple(row.get("approximation_conditions", ())),
            row.get("policy_authority_ref"),
        )
    if kind is KnowledgeKind.PROCEDURE:
        return ProcedureContent(
            row["entry_step_id"],
            tuple(
                ProcedureStep(
                    step_id=x["step_id"],
                    kind=ProcedureStepKind(x["kind"]),
                    input_refs=tuple(x["input_refs"]),
                    output_type=x["output_type"],
                    capability_id=x.get("capability_id"),
                    authority_ref=x.get("authority_ref"),
                    next_step_ids=tuple(x.get("next_step_ids", ())),
                )
                for x in row["steps"]
            ),
            row["output_type"],
        )
    if kind is KnowledgeKind.EXERCISE_FAMILY:
        return ExerciseFamilyContent(
            row["family_id"],
            tuple(row["concept_ids"]),
            row["input_schema_hash"],
            row["answer_schema_hash"],
            tuple(row["difficulty_levels"]),
        )
    if kind in {
        KnowledgeKind.TAXONOMY_EDGE,
        KnowledgeKind.PART_WHOLE_RELATION,
        KnowledgeKind.TEMPORAL_RELATION,
        KnowledgeKind.SPATIAL_RELATION,
        KnowledgeKind.RELATION_TYPE,
    }:
        return RelationContent(**row)
    if kind in {KnowledgeKind.QUANTITY_TYPE, KnowledgeKind.UNIT_DEFINITION}:
        return QuantityContent(**row)
    return TextContent(**row)
