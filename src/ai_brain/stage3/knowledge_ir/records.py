"""Strict immutable universal knowledge records.

The IR is descriptive.  It contains no Python source and grants no execution
authority; executable operations can only be referenced by capability ID.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeKind(StrEnum):
    CONCEPT = "CONCEPT"
    DEFINITION = "DEFINITION"
    ENTITY_TYPE = "ENTITY_TYPE"
    RELATION_TYPE = "RELATION_TYPE"
    TAXONOMY_EDGE = "TAXONOMY_EDGE"
    PART_WHOLE_RELATION = "PART_WHOLE_RELATION"
    QUANTITY_TYPE = "QUANTITY_TYPE"
    UNIT_DEFINITION = "UNIT_DEFINITION"
    CLAIM_SCHEMA = "CLAIM_SCHEMA"
    EQUATION_RULE = "EQUATION_RULE"
    CONSTRAINT_RULE = "CONSTRAINT_RULE"
    PROCEDURE = "PROCEDURE"
    ALGORITHM = "ALGORITHM"
    STATE_TRANSITION = "STATE_TRANSITION"
    CAUSAL_RULE = "CAUSAL_RULE"
    TEMPORAL_RELATION = "TEMPORAL_RELATION"
    SPATIAL_RELATION = "SPATIAL_RELATION"
    APPLICABILITY_CONDITION = "APPLICABILITY_CONDITION"
    EXCEPTION_RULE = "EXCEPTION_RULE"
    EXAMPLE = "EXAMPLE"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    TEST_CASE = "TEST_CASE"
    EXERCISE_FAMILY = "EXERCISE_FAMILY"
    INTERPRETATION = "INTERPRETATION"
    # A typed rule relation is needed to represent reviewed generic dependencies.
    DEPENDENCY_RULE = "DEPENDENCY_RULE"


class EpistemicCharacter(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    EMPIRICAL = "EMPIRICAL"
    APPROXIMATE = "APPROXIMATE"
    HEURISTIC = "HEURISTIC"
    NORMATIVE = "NORMATIVE"
    INTERPRETIVE = "INTERPRETIVE"
    CONTESTED = "CONTESTED"


class ExpressionKind(StrEnum):
    VARIABLE = "VARIABLE"
    CONSTANT = "CONSTANT"
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    MULTIPLY = "MULTIPLY"
    DIVIDE = "DIVIDE"
    POWER = "POWER"
    EQUAL = "EQUAL"
    INEQUALITY = "INEQUALITY"
    AND = "AND"
    OR = "OR"
    CAPABILITY_REFERENCE = "CAPABILITY_REFERENCE"


@dataclass(frozen=True)
class VariableBinding:
    variable_id: str
    value_type: str
    unit_or_dimension: str | None
    domain_role: str
    minimum: str | None = None
    maximum: str | None = None
    semantic_entity_role: str | None = None


@dataclass(frozen=True)
class Expression:
    kind: ExpressionKind
    value: str | bool | int | None = None
    children: tuple[Expression, ...] = ()
    capability_id: str | None = None


@dataclass(frozen=True)
class Applicability:
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...] = ()
    scope: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    valid_from: str | None = None
    valid_to: str | None = None
    required_capabilities: tuple[str, ...] = ()
    unsupported_cases: tuple[str, ...] = ()


class ProcedureStepKind(StrEnum):
    READ_FACT = "READ_FACT"
    INVOKE_CAPABILITY = "INVOKE_CAPABILITY"
    APPLY_VERIFIED_RULE = "APPLY_VERIFIED_RULE"
    VALIDATE_CONDITION = "VALIDATE_CONDITION"
    BRANCH_TYPED_RESULT = "BRANCH_TYPED_RESULT"
    PRODUCE_TYPED_OUTPUT = "PRODUCE_TYPED_OUTPUT"


@dataclass(frozen=True)
class ProcedureStep:
    step_id: str
    kind: ProcedureStepKind
    input_refs: tuple[str, ...]
    output_type: str
    capability_id: str | None = None
    authority_ref: str | None = None
    next_step_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TextContent:
    canonical_name_ru: str
    canonical_name_en: str
    text_ru: str
    text_en: str


@dataclass(frozen=True)
class RelationContent:
    subject_id: str
    predicate_id: str
    object_id: str


@dataclass(frozen=True)
class QuantityContent:
    value_type: str
    dimension: str
    canonical_unit: str | None


@dataclass(frozen=True)
class RuleContent:
    expression: Expression
    variables: tuple[VariableBinding, ...]
    applicability: Applicability
    approximation_conditions: tuple[str, ...] = ()
    policy_authority_ref: str | None = None


@dataclass(frozen=True)
class ProcedureContent:
    entry_step_id: str
    steps: tuple[ProcedureStep, ...]
    output_type: str


@dataclass(frozen=True)
class ExerciseFamilyContent:
    family_id: str
    concept_ids: tuple[str, ...]
    input_schema_hash: str
    answer_schema_hash: str
    difficulty_levels: tuple[str, ...]


type KnowledgeContent = (
    TextContent
    | RelationContent
    | QuantityContent
    | RuleContent
    | ProcedureContent
    | ExerciseFamilyContent
)


@dataclass(frozen=True)
class KnowledgeRecord:
    knowledge_id: str
    domain_id: str
    kind: KnowledgeKind
    schema_version: int
    epistemic_character: EpistemicCharacter
    provenance_refs: tuple[str, ...]
    dependencies: tuple[str, ...]
    applicability_refs: tuple[str, ...]
    required_capability_ids: tuple[str, ...]
    created_at: str
    content: KnowledgeContent
    content_hash: str
