"""Canonical, exact-field serialization for Universal Knowledge IR v2."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from typing import Any

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.knowledge_ir.records import *
from ai_brain.stage3.knowledge_ir.validation import validate_record

_TOP = {field.name for field in fields(KnowledgeRecord)}
_CONTENT: dict[KnowledgeKind, type] = {
    KnowledgeKind.CONCEPT: ConceptContent,
    KnowledgeKind.DEFINITION: DefinitionContent,
    KnowledgeKind.ENTITY_TYPE: EntityTypeContent,
    KnowledgeKind.RELATION_TYPE: RelationTypeContent,
    KnowledgeKind.TAXONOMY_EDGE: RelationContent,
    KnowledgeKind.PART_WHOLE_RELATION: RelationContent,
    KnowledgeKind.QUANTITY_TYPE: QuantityContent,
    KnowledgeKind.UNIT_DEFINITION: UnitDefinitionContent,
    KnowledgeKind.CLAIM_SCHEMA: ClaimSchemaContent,
    KnowledgeKind.EQUATION_RULE: RuleContent,
    KnowledgeKind.CONSTRAINT_RULE: RuleContent,
    KnowledgeKind.PROCEDURE: ProcedureContent,
    KnowledgeKind.ALGORITHM: RuleContent,
    KnowledgeKind.STATE_TRANSITION: RuleContent,
    KnowledgeKind.CAUSAL_RULE: CausalClaimContent,
    KnowledgeKind.TEMPORAL_RELATION: TemporalRelationContent,
    KnowledgeKind.SPATIAL_RELATION: SpatialRelationContent,
    KnowledgeKind.APPLICABILITY_CONDITION: ApplicabilityConditionContent,
    KnowledgeKind.EXCEPTION_RULE: ExceptionRuleContent,
    KnowledgeKind.EXAMPLE: ExampleContent,
    KnowledgeKind.COUNTEREXAMPLE: CounterexampleContent,
    KnowledgeKind.TEST_CASE: TestCaseContent,
    KnowledgeKind.EXERCISE_FAMILY: ExerciseFamilyContent,
    KnowledgeKind.INTERPRETATION: InterpretationContent,
    KnowledgeKind.DEPENDENCY_RULE: RuleContent,
}


def dump_record(record: KnowledgeRecord) -> str:
    validate_record(record)
    return canonical_json(asdict(record)) + "\n"


def load_record(text: str) -> KnowledgeRecord:
    row = json.loads(text, object_pairs_hook=_strict_object)
    _exact(row, _TOP, "knowledge record")
    kind = KnowledgeKind(_plain(row, "kind", str))
    result = KnowledgeRecord(
        knowledge_id=_plain(row, "knowledge_id", str),
        domain_id=_plain(row, "domain_id", str),
        kind=kind,
        schema_version=_plain(row, "schema_version", int),
        epistemic_character=EpistemicCharacter(_plain(row, "epistemic_character", str)),
        provenance_refs=_tuple_of(row, "provenance_refs", str),
        dependencies=_tuple_of(row, "dependencies", str),
        applicability_refs=_tuple_of(row, "applicability_refs", str),
        required_capability_ids=_tuple_of(row, "required_capability_ids", str),
        created_at=_plain(row, "created_at", str),
        content=_content_from_dict(kind, _plain(row, "content", dict)),
        content_hash=_plain(row, "content_hash", str),
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


def _exact(row: dict, expected: set[str], label: str) -> None:
    if not isinstance(row, dict) or set(row) != expected:
        raise ValueError(f"invalid exact {label} field set")


def _plain(row: dict, key: str, expected: type):
    value = row[key]
    if expected is int and isinstance(value, bool):
        raise TypeError(f"{key} has wrong type")
    if not isinstance(value, expected):
        raise TypeError(f"{key} has wrong type")
    return value


def _tuple_of(row: dict, key: str, expected: type):
    value = _plain(row, key, list)
    if any(not isinstance(item, expected) for item in value):
        raise ValueError(f"{key} has wrong item type")
    return tuple(value)


def _dc(row: dict, cls: type, **overrides):
    _exact(row, {field.name for field in fields(cls)}, cls.__name__)
    return cls(**{**row, **overrides})


def _dimension(row: dict) -> DimensionVector:
    value = _dc(row, DimensionVector)
    if any(
        isinstance(x, bool) or not isinstance(x, int) for x in asdict(value).values()
    ):
        raise ValueError("dimension exponents must be exact integers")
    return value


def _entity(row: dict | None) -> EntityTypeRef | None:
    if row is None:
        return None
    return _dc(row, EntityTypeRef)


def _unit(row: dict | None) -> UnitRef | None:
    if row is None:
        return None
    return _dc(row, UnitRef, dimension=_dimension(row["dimension"]))


def _quantity(row: dict | None) -> QuantityTypeRef | None:
    if row is None:
        return None
    return _dc(
        row,
        QuantityTypeRef,
        dimension=_dimension(row["dimension"]),
        canonical_unit=_unit(row["canonical_unit"]),
    )


def _value_type(row: dict) -> ValueTypeRef:
    return _dc(
        row,
        ValueTypeRef,
        kind=ValueTypeKind(row["kind"]),
        entity_type=_entity(row["entity_type"]),
        quantity_type=_quantity(row["quantity_type"]),
    )


def _expression(row: dict) -> Expression:
    return _dc(
        row,
        Expression,
        kind=ExpressionKind(row["kind"]),
        children=tuple(_expression(x) for x in _plain(row, "children", list)),
        result_type=(
            _value_type(row["result_type"]) if row["result_type"] is not None else None
        ),
    )


def _binding(row: dict) -> VariableBinding:
    return _dc(row, VariableBinding, value_type=_value_type(row["value_type"]))


def _applicability(row: dict) -> Applicability:
    _exact(row, {field.name for field in fields(Applicability)}, "Applicability")
    values = dict(row)
    for key in (
        "preconditions",
        "postconditions",
        "scope",
        "assumptions",
        "exclusions",
        "exceptions",
        "required_capabilities",
        "unsupported_cases",
    ):
        values[key] = _tuple_of(row, key, str)
    return Applicability(**values)


def _content_from_dict(kind: KnowledgeKind, row: dict) -> KnowledgeContent:
    cls = _CONTENT[kind]
    _exact(row, {field.name for field in fields(cls)}, f"{kind.value} content")
    if cls is ConceptContent:
        return ConceptContent(**row)
    if cls is DefinitionContent:
        return DefinitionContent(**row)
    if cls is EntityTypeContent:
        return EntityTypeContent(
            **{**row, "parent_entity_type_ids": tuple(row["parent_entity_type_ids"])}
        )
    if cls is RelationTypeContent:
        return RelationTypeContent(
            **{
                **row,
                "subject_type": _entity(row["subject_type"]),
                "object_type": _entity(row["object_type"]),
            }
        )
    if cls is RelationContent:
        return RelationContent(
            **{
                **row,
                "subject_type": _entity(row["subject_type"]),
                "object_type": _entity(row["object_type"]),
            }
        )
    if cls is QuantityContent:
        return QuantityContent(
            **{**row, "quantity_type": _quantity(row["quantity_type"])}
        )
    if cls is UnitDefinitionContent:
        return UnitDefinitionContent(**{**row, "unit": _unit(row["unit"])})
    if cls is ClaimSchemaContent:
        return ClaimSchemaContent(
            **{
                **row,
                "subject_type": _entity(row["subject_type"]),
                "object_type": _value_type(row["object_type"]),
                "qualifier_ids": tuple(row["qualifier_ids"]),
                "parameters": tuple(tuple(item) for item in row["parameters"]),
                "generic_constraints": tuple(row["generic_constraints"]),
                "preconditions": tuple(row["preconditions"]),
                "postconditions": tuple(row["postconditions"]),
                "declared_exceptions": tuple(row["declared_exceptions"]),
                "examples": tuple(row["examples"]),
            }
        )
    if cls is RuleContent:
        return RuleContent(
            _expression(row["expression"]),
            tuple(_binding(x) for x in row["variables"]),
            _applicability(row["applicability"]),
            tuple(row["approximation_conditions"]),
            row["policy_authority_ref"],
        )
    if cls is ProcedureContent:
        return ProcedureContent(
            row["entry_step_id"],
            tuple(
                _dc(
                    item,
                    ProcedureStep,
                    kind=ProcedureStepKind(item["kind"]),
                    input_refs=tuple(item["input_refs"]),
                    output_type=_value_type(item["output_type"]),
                    next_step_ids=tuple(item["next_step_ids"]),
                )
                for item in row["steps"]
            ),
            _value_type(row["output_type"]),
        )
    if cls is ApplicabilityConditionContent:
        return ApplicabilityConditionContent(
            row["condition_id"],
            _expression(row["expression"]),
            tuple(_binding(x) for x in row["variables"]),
        )
    tuple_fields = {
        EntityTypeContent: ("parent_entity_type_ids",),
        ExceptionRuleContent: ("exception_condition_ids",),
        ExampleContent: ("referenced_ids",),
        CounterexampleContent: ("refuted_record_ids",),
        TestCaseContent: ("input_values", "expected_values"),
        ExerciseFamilyContent: ("concept_ids", "difficulty_levels"),
        InterpretationContent: ("supported_record_ids", "contrast_record_ids"),
    }.get(cls, ())
    values: dict[str, Any] = dict(row)
    for key in tuple_fields:
        values[key] = tuple(tuple(x) if isinstance(x, list) else x for x in row[key])
    return cls(**values)


def load_content(kind: KnowledgeKind, row: dict) -> KnowledgeContent:
    """Load one exact tagged content object without constructing a record."""
    return _content_from_dict(kind, row)
