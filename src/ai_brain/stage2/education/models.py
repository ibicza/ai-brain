"""Immutable educational graphs, exercises, grades, hints, and sessions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Any


class GraphNodeKind(StrEnum):
    GIVEN_VALUE = "GIVEN_VALUE"
    FACT_LOOKUP = "FACT_LOOKUP"
    FORMULA_PARSE = "FORMULA_PARSE"
    FORMULA_COMPOSITION = "FORMULA_COMPOSITION"
    STOICHIOMETRIC_COUNT = "STOICHIOMETRIC_COUNT"
    UNIT_NORMALIZATION = "UNIT_NORMALIZATION"
    ATOMIC_WEIGHT_LOOKUP = "ATOMIC_WEIGHT_LOOKUP"
    MULTIPLY = "MULTIPLY"
    ADD = "ADD"
    DIVIDE = "DIVIDE"
    MOLE_RELATION = "MOLE_RELATION"
    AVOGADRO_RELATION = "AVOGADRO_RELATION"
    ROUND_DISPLAY = "ROUND_DISPLAY"
    FINAL_RESULT = "FINAL_RESULT"
    SOURCE_REFERENCE = "SOURCE_REFERENCE"
    WARNING = "WARNING"


class EducationalDimension(StrEnum):
    DIMENSIONLESS = "DIMENSIONLESS"
    COUNT = "COUNT"
    MASS = "MASS"
    AMOUNT = "AMOUNT"
    INVERSE_AMOUNT = "INVERSE_AMOUNT"
    MOLAR_MASS = "MOLAR_MASS"
    ENTITY_COUNT = "ENTITY_COUNT"
    ATOMIC_WEIGHT = "ATOMIC_WEIGHT"
    FORMULA = "FORMULA"
    COMPOSITION = "COMPOSITION"
    INTERVAL_MOLAR_MASS = "INTERVAL_MOLAR_MASS"


class ActorIdentityType(StrEnum):
    TRUSTED_PROCESS = "TRUSTED_PROCESS"
    MODEL = "MODEL"
    USER = "USER"


class ExplanationSegmentKind(StrEnum):
    HEADING = "HEADING"
    GIVEN = "GIVEN"
    FACT = "FACT"
    FORMULA = "FORMULA"
    OPERATION = "OPERATION"
    SUBSTITUTION = "SUBSTITUTION"
    INTERMEDIATE_RESULT = "INTERMEDIATE_RESULT"
    ROUNDING = "ROUNDING"
    FINAL_RESULT = "FINAL_RESULT"
    WARNING = "WARNING"
    SOURCE_CITATION = "SOURCE_CITATION"
    GRAPH_REFERENCE = "GRAPH_REFERENCE"


class GraphEdgeKind(StrEnum):
    DEPENDS_ON = "DEPENDS_ON"
    USES_FACT = "USES_FACT"
    USES_FORMULA_TERM = "USES_FORMULA_TERM"
    NORMALIZES_UNIT = "NORMALIZES_UNIT"
    CONTRIBUTES_TO = "CONTRIBUTES_TO"
    ROUNDS_FOR_DISPLAY = "ROUNDS_FOR_DISPLAY"
    SUPPORTS_RESULT = "SUPPORTS_RESULT"
    CITES_SOURCE = "CITES_SOURCE"
    WARNS_ABOUT = "WARNS_ABOUT"


class ExplanationMode(StrEnum):
    CONCISE = "CONCISE"
    FULL = "FULL"
    CHECK_ONLY = "CHECK_ONLY"
    HINT_ONLY = "HINT_ONLY"
    SOLUTION_AFTER_ATTEMPT = "SOLUTION_AFTER_ATTEMPT"


class ExerciseFamily(StrEnum):
    FACT_RETRIEVAL = "FACT_RETRIEVAL"
    FORMULA_COMPOSITION = "FORMULA_COMPOSITION"
    MOLAR_MASS_SIMPLE = "MOLAR_MASS_SIMPLE"
    MOLAR_MASS_GROUPED = "MOLAR_MASS_GROUPED"
    MASS_AMOUNT = "MASS_AMOUNT"
    AMOUNT_ENTITIES = "AMOUNT_ENTITIES"


class ExerciseSplitAxis(StrEnum):
    FORMULA_STRUCTURE_HOLDOUT = "FORMULA_STRUCTURE_HOLDOUT"
    ELEMENT_COMBINATION_HOLDOUT = "ELEMENT_COMBINATION_HOLDOUT"
    NUMERIC_RANGE_HOLDOUT = "NUMERIC_RANGE_HOLDOUT"
    UNIT_DIRECTION_HOLDOUT = "UNIT_DIRECTION_HOLDOUT"
    TEMPLATE_KEY_PARTITION = "TEMPLATE_KEY_PARTITION"
    LANGUAGE_ASSIGNMENT_PARTITION = "LANGUAGE_ASSIGNMENT_PARTITION"
    MULTI_STEP_COMPOSITION_HOLDOUT = "MULTI_STEP_COMPOSITION_HOLDOUT"


class StudentAnswerKind(StrEnum):
    NUMERIC_WITH_UNIT = "NUMERIC_WITH_UNIT"
    FORMULA_COMPOSITION = "FORMULA_COMPOSITION"
    ELEMENT_COUNT_MAP = "ELEMENT_COUNT_MAP"
    ATOMIC_WEIGHT_INTERVAL = "ATOMIC_WEIGHT_INTERVAL"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    STEP_SEQUENCE = "STEP_SEQUENCE"
    FREE_TEXT_ASSISTIVE = "FREE_TEXT_ASSISTIVE"


class AnswerParseStatus(StrEnum):
    PARSED = "PARSED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    INVALID = "INVALID"


class GradingStatus(StrEnum):
    CORRECT = "CORRECT"
    CORRECT_EQUIVALENT_UNIT = "CORRECT_EQUIVALENT_UNIT"
    CORRECT_WITH_ACCEPTABLE_ROUNDING = "CORRECT_WITH_ACCEPTABLE_ROUNDING"
    CORRECT_FINAL_UNVERIFIED_STEPS = "CORRECT_FINAL_UNVERIFIED_STEPS"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    INCORRECT = "INCORRECT"
    AMBIGUOUS_ANSWER = "AMBIGUOUS_ANSWER"
    INVALID_ANSWER = "INVALID_ANSWER"
    STALE_EXERCISE = "STALE_EXERCISE"


class MisconceptionCode(StrEnum):
    FORMULA_PARSE_ERROR = "FORMULA_PARSE_ERROR"
    UNKNOWN_ELEMENT_SYMBOL = "UNKNOWN_ELEMENT_SYMBOL"
    WRONG_SYMBOL_CASE = "WRONG_SYMBOL_CASE"
    SUBSCRIPT_IGNORED = "SUBSCRIPT_IGNORED"
    GROUP_MULTIPLIER_IGNORED = "GROUP_MULTIPLIER_IGNORED"
    ELEMENT_COUNT_WRONG = "ELEMENT_COUNT_WRONG"
    ATOMIC_WEIGHT_WRONG = "ATOMIC_WEIGHT_WRONG"
    ATOMIC_WEIGHT_POLICY_MISMATCH = "ATOMIC_WEIGHT_POLICY_MISMATCH"
    MOLAR_MASS_TERM_WRONG = "MOLAR_MASS_TERM_WRONG"
    MOLAR_MASS_SUM_WRONG = "MOLAR_MASS_SUM_WRONG"
    MULTIPLY_INSTEAD_OF_DIVIDE = "MULTIPLY_INSTEAD_OF_DIVIDE"
    DIVIDE_INSTEAD_OF_MULTIPLY = "DIVIDE_INSTEAD_OF_MULTIPLY"
    GRAM_KILOGRAM_CONVERSION_ERROR = "GRAM_KILOGRAM_CONVERSION_ERROR"
    MOL_MMOL_CONVERSION_ERROR = "MOL_MMOL_CONVERSION_ERROR"
    AVOGADRO_FACTOR_MISSING = "AVOGADRO_FACTOR_MISSING"
    AVOGADRO_FACTOR_EXTRA = "AVOGADRO_FACTOR_EXTRA"
    FORMULA_ENTITY_ATOM_MULTIPLIER_MISSING = "FORMULA_ENTITY_ATOM_MULTIPLIER_MISSING"
    TARGET_ELEMENT_MULTIPLIER_WRONG = "TARGET_ELEMENT_MULTIPLIER_WRONG"
    UNIT_MISSING = "UNIT_MISSING"
    UNIT_WRONG_DIMENSION = "UNIT_WRONG_DIMENSION"
    ROUNDING_TOO_EARLY = "ROUNDING_TOO_EARLY"
    ROUNDING_OUTSIDE_POLICY = "ROUNDING_OUTSIDE_POLICY"
    INTERVAL_COLLAPSED_TO_MIDPOINT = "INTERVAL_COLLAPSED_TO_MIDPOINT"
    ARITHMETIC_ERROR = "ARITHMETIC_ERROR"
    UNCLASSIFIED_ERROR = "UNCLASSIFIED_ERROR"
    AMBIGUOUS_DIAGNOSIS = "AMBIGUOUS_DIAGNOSIS"


class DiagnosisConfidence(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    AMBIGUOUS = "AMBIGUOUS"


class HintLevel(IntEnum):
    ORIENT = 1
    NEXT_STEP = 2
    SUBSTITUTION = 3
    PARTIAL_CALCULATION = 4
    FULL_SOLUTION = 5


class TutorSessionStatus(StrEnum):
    PRESENTED = "PRESENTED"
    ATTEMPTED = "ATTEMPTED"
    HINTED = "HINTED"
    SOLVED = "SOLVED"
    SOLUTION_REVEALED = "SOLUTION_REVEALED"
    ABANDONED = "ABANDONED"


class EducationalReplayStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE_DOMAIN = "STALE_DOMAIN"
    STALE_FACT_MEMORY = "STALE_FACT_MEMORY"
    STALE_CLAIM = "STALE_CLAIM"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    STALE_SOURCE = "STALE_SOURCE"
    STALE_UPSTREAM_SOURCE = "STALE_UPSTREAM_SOURCE"
    STALE_SOURCE_CHAIN = "STALE_SOURCE_CHAIN"
    STALE_TOOL = "STALE_TOOL"
    STALE_EXERCISE_SPEC = "STALE_EXERCISE_SPEC"
    STALE_COMPILATION_RECEIPT = "STALE_COMPILATION_RECEIPT"
    STALE_ANSWER_KEY = "STALE_ANSWER_KEY"
    STALE_GRADING_POLICY = "STALE_GRADING_POLICY"
    STALE_HINT_POLICY = "STALE_HINT_POLICY"
    INVALID_GRAPH = "INVALID_GRAPH"
    INVALID_SOURCE_RESULT = "INVALID_SOURCE_RESULT"
    INVALID_ARTIFACT = "INVALID_ARTIFACT"
    INVALID_SESSION = "INVALID_SESSION"


class EducationalRouteKind(StrEnum):
    EXPLAIN = "EXPLAIN"
    GENERATE_EXERCISE = "GENERATE_EXERCISE"
    CHECK_ANSWER = "CHECK_ANSWER"
    HINT = "HINT"
    SHOW_SOLUTION = "SHOW_SOLUTION"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class EducationalGraphNode:
    node_id: str
    kind: GraphNodeKind
    label: str
    operation: str | None
    input_node_ids: tuple[str, ...]
    exact_inputs: tuple[str, ...]
    exact_output: Any
    unit: str | None
    dimension: EducationalDimension | None
    display_output: str | None
    policy_version: str
    claim_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_hashes: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    metadata: dict[str, Any]
    node_hash: str


@dataclass(frozen=True)
class EducationalGraphEdge:
    source_node_id: str
    target_node_id: str
    kind: GraphEdgeKind
    edge_hash: str


@dataclass(frozen=True)
class EducationalDerivationGraph:
    graph_id: str
    domain_id: str
    domain_version: str
    source_result_type: str
    source_result_hash: str
    request_hash: str
    route_decision_hash: str | None
    fact_memory_snapshot_hash: str
    knowledge_snapshot_hash: str
    formula_ast_hash: str | None
    tool_implementation_hash: str | None
    calculation_policy_version: str
    rounding_policy_hash: str
    source_chain_version: str
    source_chain_hash: str
    nodes: tuple[EducationalGraphNode, ...]
    edges: tuple[EducationalGraphEdge, ...]
    root_result_node_id: str
    claim_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    source_hashes: tuple[str, ...]
    derivation_hashes: tuple[str, ...]
    created_at: str
    schema_version: int
    graph_hash: str
    source_result_artifact: dict[str, Any]


@dataclass(frozen=True)
class ExplanationArtifact:
    graph_hash: str
    source_result_hash: str
    language: str
    mode: ExplanationMode
    text: str
    numeric_node_ids: tuple[str, ...]
    formula_node_ids: tuple[str, ...]
    source_node_ids: tuple[str, ...]
    rendering_version: str
    explanation_hash: str
    plan_hash: str
    grading_result_hash: str | None
    session_id: str | None
    session_state_hash: str | None


@dataclass(frozen=True)
class ExplanationSegment:
    kind: ExplanationSegmentKind
    node_ids: tuple[str, ...]
    permitted_fields: tuple[str, ...]
    segment_hash: str


@dataclass(frozen=True)
class ExplanationPlan:
    graph_hash: str
    source_result_hash: str
    language: str
    mode: ExplanationMode
    segments: tuple[ExplanationSegment, ...]
    rendering_version: str
    plan_hash: str


@dataclass(frozen=True)
class ExerciseSpec:
    exercise_id: str
    family: ExerciseFamily
    domain_version: str
    difficulty_tier: int
    learning_objectives: tuple[str, ...]
    required_concepts: tuple[str, ...]
    parameter_constraints: dict[str, Any]
    accepted_answer_type: StudentAnswerKind
    allowed_units: tuple[str, ...]
    grading_policy: str
    hint_ladder: tuple[int, ...]
    template_ids_ru: tuple[str, ...]
    template_ids_en: tuple[str, ...]
    source_policy: str
    schema_version: int
    spec_hash: str


@dataclass(frozen=True)
class CounterfactualAnswer:
    diagnosis: MisconceptionCode
    answer: dict[str, Any]
    matching_node_ids: tuple[str, ...]
    counterfactual_hash: str


@dataclass(frozen=True)
class ExerciseInstance:
    instance_id: str
    exercise_spec_hash: str
    deterministic_seed: int
    language: str
    question_text: str
    structured_givens: dict[str, Any]
    hidden_answer_graph_hash: str
    hidden_expected_answer: dict[str, Any]
    accepted_equivalent_forms: tuple[dict[str, Any], ...]
    provenance_dependencies: tuple[str, ...]
    difficulty_metadata: dict[str, Any]
    split_memberships: tuple[tuple[str, str, str], ...]
    counterfactuals: tuple[CounterfactualAnswer, ...]
    generated_at: str
    schema_version: int
    instance_hash: str
    semantic_key_hash: str
    compilation_receipt_hash: str


@dataclass(frozen=True)
class PresentedExercise:
    session_id: str
    exercise_id: str
    language: str
    question_text: str
    structured_public_givens: dict[str, Any]
    difficulty_metadata: dict[str, Any]
    learning_objectives: tuple[str, ...]
    accepted_answer_format: str
    schema_version: int
    presentation_hash: str


@dataclass(frozen=True)
class SemanticExerciseKey:
    exercise_family: ExerciseFamily
    subject: str
    predicate: str | None
    numeric_givens: tuple[tuple[str, str], ...]
    source_unit: str | None
    target_unit: str | None
    entity_basis: str | None
    requested_precision: int | None
    answer_semantics_hash: str
    answer_graph_hash: str
    semantic_key_hash: str


@dataclass(frozen=True)
class EducationalCompilationReceipt:
    compilation_id: str
    compiler_identity: str
    actor_identity_type: ActorIdentityType
    compilation_policy_version: str
    chemistry_domain_manifest_hash: str
    fact_memory_snapshot_hash: str
    source_chain_hash: str
    tool_id: str
    canonical_arguments: dict[str, Any]
    tool_implementation_manifest_hash: str
    knowledge_snapshot_hash: str
    exact_result_hash: str
    educational_graph_hash: str
    exercise_spec_hash: str | None
    generated_at: str
    receipt_hash: str


@dataclass(frozen=True)
class EducationalCatalogEntryV2:
    semantic_key: SemanticExerciseKey
    exercise_spec: ExerciseSpec
    internal_instance: ExerciseInstance
    graph: EducationalDerivationGraph
    compilation_receipt: EducationalCompilationReceipt
    entry_hash: str


@dataclass(frozen=True)
class EducationalCatalogManifestV2:
    chemistry_domain_manifest_hash: str
    fact_memory_snapshot_hash: str
    source_chain_hash: str
    tool_manifest_hashes: tuple[tuple[str, str], ...]
    generator_version: str
    entry_hashes: tuple[str, ...]
    split_manifest_hashes: tuple[str, ...]
    schema_version: int
    catalog_hash: str


@dataclass(frozen=True)
class StudentAnswer:
    answer_kind: StudentAnswerKind
    raw_input_hash: str
    interpreted_answer: dict[str, Any] | None
    parse_status: AnswerParseStatus
    issues: tuple[str, ...]
    confirmed: bool
    answer_hash: str


@dataclass(frozen=True)
class ErrorDiagnosis:
    code: MisconceptionCode
    confidence: DiagnosisConfidence
    counterfactual_value: dict[str, Any] | None
    matching_node_ids: tuple[str, ...]
    clarification: str | None
    diagnosis_hash: str


@dataclass(frozen=True)
class GradingResult:
    attempt_id: str
    exercise_id: str
    exercise_hash: str
    student_answer_hash: str
    interpreted_answer: dict[str, Any] | None
    parse_status: AnswerParseStatus
    correctness_status: GradingStatus
    score: str
    maximum_score: str
    correct_nodes: tuple[str, ...]
    incorrect_nodes: tuple[str, ...]
    first_incorrect_node: str | None
    error_diagnoses: tuple[ErrorDiagnosis, ...]
    unit_comparison: str
    rounding_comparison: str
    answer_graph_hash: str
    created_at: str
    schema_version: int
    result_hash: str


@dataclass(frozen=True)
class HintPlan:
    exercise_id: str
    graph_hash: str
    node_order: tuple[str, ...]
    policy_version: str
    grading_result_hash: str | None
    diagnosis_hashes: tuple[str, ...]
    plan_hash: str


@dataclass(frozen=True)
class HintArtifact:
    exercise_id: str
    graph_hash: str
    level: HintLevel
    language: str
    text: str
    revealed_node_ids: tuple[str, ...]
    diagnosis_codes: tuple[MisconceptionCode, ...]
    final_answer_revealed: bool
    policy_version: str
    plan_hash: str
    grading_result_hash: str | None
    diagnosis_hashes: tuple[str, ...]
    hint_hash: str


@dataclass(frozen=True)
class TutorEvent:
    event_id: str
    session_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    previous_event_hash: str | None
    created_at: str
    event_hash: str


@dataclass(frozen=True)
class TutorSession:
    session_id: str
    exercise_id: str
    exercise_hash: str
    language: str
    attempt_hashes: tuple[str, ...]
    grading_result_hashes: tuple[str, ...]
    hint_hashes: tuple[str, ...]
    status: TutorSessionStatus
    graph_hash: str
    domain_dependencies: tuple[str, ...]
    created_at: str
    updated_at: str
    last_event_hash: str | None
    schema_version: int
    session_hash: str


@dataclass(frozen=True)
class PublicTutorSessionHandle:
    session_id: str
    status: str


@dataclass(frozen=True)
class PublicExercise:
    session: PublicTutorSessionHandle
    exercise_id: str
    language: str
    question: str
    structured_givens: dict[str, Any]
    difficulty: dict[str, Any]
    learning_objectives: tuple[str, ...]
    accepted_answer_format: str


@dataclass(frozen=True)
class PublicExplanation:
    status: str
    language: str
    mode: str
    text: str | None
    confirmation_required: bool


@dataclass(frozen=True)
class PublicSubmissionResult:
    parse_status: str
    status: str
    score: str
    maximum_score: str
    diagnoses: tuple[str, ...]
    feedback: str
    session: PublicTutorSessionHandle


@dataclass(frozen=True)
class PublicHint:
    level: int
    text: str
    session: PublicTutorSessionHandle


@dataclass(frozen=True)
class PublicSolution:
    text: str
    session: PublicTutorSessionHandle


@dataclass(frozen=True)
class PublicReplayStatus:
    session_id: str
    status: str
    session_status: str | None


@dataclass(frozen=True)
class EducationalRoute:
    kind: EducationalRouteKind
    language: str
    payload: dict[str, Any]
    parser_evidence: dict[str, Any]
    route_hash: str


@dataclass(frozen=True)
class EducationalRouteReceipt:
    original_request_hash: str
    controlled_parser_version: str
    route_kind: EducationalRouteKind
    session_id: str | None
    presented_exercise_hash: str | None
    prepared_response_hash: str | None
    requested_action: str
    dependency_snapshot: tuple[str, ...]
    created_at: str
    receipt_hash: str
