"""Immutable Universal Knowledge IR v2 records.

The IR is descriptive data. It never contains executable source and grants no
execution authority; executable work is referenced only by installed capability
IDs and verified provider manifests.
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
    DEPENDENCY_RULE = "DEPENDENCY_RULE"


class EpistemicCharacter(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    EMPIRICAL = "EMPIRICAL"
    APPROXIMATE = "APPROXIMATE"
    HEURISTIC = "HEURISTIC"
    NORMATIVE = "NORMATIVE"
    INTERPRETIVE = "INTERPRETIVE"
    CONTESTED = "CONTESTED"


class ValueTypeKind(StrEnum):
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    RATIONAL = "RATIONAL"
    STRING = "STRING"
    ENTITY = "ENTITY"
    QUANTITY = "QUANTITY"
    VOID = "VOID"


@dataclass(frozen=True)
class DimensionVector:
    length: int = 0
    mass: int = 0
    time: int = 0
    electric_current: int = 0
    temperature: int = 0
    amount: int = 0
    luminous_intensity: int = 0


@dataclass(frozen=True)
class EntityTypeRef:
    entity_type_id: str


@dataclass(frozen=True)
class UnitRef:
    unit_id: str
    dimension: DimensionVector
    scale_numerator: int = 1
    scale_denominator: int = 1


@dataclass(frozen=True)
class QuantityTypeRef:
    quantity_type_id: str
    dimension: DimensionVector
    canonical_unit: UnitRef | None = None


@dataclass(frozen=True)
class ValueTypeRef:
    kind: ValueTypeKind
    entity_type: EntityTypeRef | None = None
    quantity_type: QuantityTypeRef | None = None


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
    value_type: ValueTypeRef
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
    result_type: ValueTypeRef | None = None


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
    output_type: ValueTypeRef
    capability_id: str | None = None
    authority_ref: str | None = None
    next_step_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConceptContent:
    canonical_name_ru: str
    canonical_name_en: str
    description_ru: str
    description_en: str


@dataclass(frozen=True)
class DefinitionContent:
    term_id: str
    definition_ru: str
    definition_en: str


@dataclass(frozen=True)
class EntityTypeContent:
    entity_type_id: str
    canonical_name_ru: str
    canonical_name_en: str
    parent_entity_type_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationTypeContent:
    predicate_id: str
    subject_type: EntityTypeRef
    object_type: EntityTypeRef
    transitive: bool
    symmetric: bool


@dataclass(frozen=True)
class RelationContent:
    subject_id: str
    predicate_id: str
    object_id: str
    subject_type: EntityTypeRef
    object_type: EntityTypeRef


@dataclass(frozen=True)
class QuantityContent:
    quantity_type: QuantityTypeRef
    canonical_name_ru: str
    canonical_name_en: str


@dataclass(frozen=True)
class UnitDefinitionContent:
    unit: UnitRef
    symbol: str
    canonical_name_ru: str
    canonical_name_en: str


@dataclass(frozen=True)
class ClaimSchemaContent:
    subject_type: EntityTypeRef
    predicate_id: str
    object_type: ValueTypeRef
    qualifier_ids: tuple[str, ...] = ()
    receiver_type: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()
    return_type: str | None = None
    generic_constraints: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    declared_exceptions: tuple[str, ...] = ()
    deprecated_since: str | None = None
    examples: tuple[str, ...] = ()
    java_callable_kind: str | None = None
    resolved_parameter_types: tuple[str, ...] = ()
    parameter_array_dimensions: tuple[int, ...] = ()
    parameter_varargs: tuple[bool, ...] = ()
    resolved_return_type: str | None = None
    return_array_dimensions: int = 0
    method_type_parameters: tuple[str, ...] = ()
    intersection_bounds: tuple[tuple[str, ...], ...] = ()
    first_bound_erasures: tuple[str, ...] = ()
    resolved_declared_exceptions: tuple[str, ...] = ()
    modifiers: tuple[str, ...] = ()
    accessibility: str | None = None
    enclosing_type_accessibility: str | None = None
    module_name: str | None = None
    package_exported: bool | None = None


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
    output_type: ValueTypeRef


@dataclass(frozen=True)
class TemporalRelationContent:
    subject_id: str
    predicate_id: str
    object_id: str
    start: str | None
    end: str | None


@dataclass(frozen=True)
class SpatialRelationContent:
    subject_id: str
    predicate_id: str
    object_id: str
    reference_frame: str


@dataclass(frozen=True)
class CausalClaimContent:
    cause_id: str
    effect_id: str
    claim_text: str
    mechanism: str | None = None


@dataclass(frozen=True)
class ApplicabilityConditionContent:
    condition_id: str
    expression: Expression
    variables: tuple[VariableBinding, ...]


@dataclass(frozen=True)
class ExceptionRuleContent:
    rule_id: str
    exception_condition_ids: tuple[str, ...]
    effect_text: str


@dataclass(frozen=True)
class ExampleContent:
    statement: str
    referenced_ids: tuple[str, ...]


@dataclass(frozen=True)
class CounterexampleContent:
    statement: str
    refuted_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class TestCaseContent:
    target_record_id: str
    input_values: tuple[tuple[str, str], ...]
    expected_values: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExerciseFamilyContent:
    family_id: str
    concept_ids: tuple[str, ...]
    input_schema_hash: str
    answer_schema_hash: str
    difficulty_levels: tuple[str, ...]


@dataclass(frozen=True)
class InterpretationContent:
    claim_text: str
    perspective: str
    supported_record_ids: tuple[str, ...]
    contrast_record_ids: tuple[str, ...] = ()


type KnowledgeContent = (
    ConceptContent
    | DefinitionContent
    | EntityTypeContent
    | RelationTypeContent
    | RelationContent
    | QuantityContent
    | UnitDefinitionContent
    | ClaimSchemaContent
    | RuleContent
    | ProcedureContent
    | TemporalRelationContent
    | SpatialRelationContent
    | CausalClaimContent
    | ApplicabilityConditionContent
    | ExceptionRuleContent
    | ExampleContent
    | CounterexampleContent
    | TestCaseContent
    | ExerciseFamilyContent
    | InterpretationContent
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


# Compatibility import only. No v2 kind maps to a generic fallback.
TextContent = ConceptContent
