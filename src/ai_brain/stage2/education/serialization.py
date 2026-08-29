"""Strict JSON reconstruction for persisted educational artifacts."""

from __future__ import annotations

from typing import Any, TypeVar

from ai_brain.stage2.education.models import (
    ActorIdentityType,
    AnswerParseStatus,
    CounterfactualAnswer,
    DiagnosisConfidence,
    EducationalCompilationReceipt,
    EducationalDerivationGraph,
    EducationalDimension,
    EducationalGraphEdge,
    EducationalGraphNode,
    ErrorDiagnosis,
    ExerciseFamily,
    ExerciseInstance,
    ExerciseSpec,
    ExplanationArtifact,
    ExplanationMode,
    ExplanationPlan,
    ExplanationSegment,
    ExplanationSegmentKind,
    GradingResult,
    GradingStatus,
    GraphEdgeKind,
    GraphNodeKind,
    HintArtifact,
    HintLevel,
    HintPlan,
    MisconceptionCode,
    PresentedExercise,
    StudentAnswer,
    StudentAnswerKind,
    TutorEvent,
    TutorSession,
    TutorSessionStatus,
)

T = TypeVar("T")


def graph_from_dict(row: dict[str, Any]) -> EducationalDerivationGraph:
    _exact(row, set(EducationalDerivationGraph.__dataclass_fields__))
    return EducationalDerivationGraph(
        **{
            **row,
            "nodes": tuple(
                EducationalGraphNode(
                    **{
                        **node,
                        "kind": GraphNodeKind(node["kind"]),
                        "dimension": EducationalDimension(node["dimension"])
                        if node["dimension"] is not None
                        else None,
                        "input_node_ids": tuple(node["input_node_ids"]),
                        "exact_inputs": tuple(node["exact_inputs"]),
                        "claim_ids": tuple(node["claim_ids"]),
                        "evidence_hashes": tuple(node["evidence_hashes"]),
                        "source_hashes": tuple(node["source_hashes"]),
                        "derivation_hashes": tuple(node["derivation_hashes"]),
                    }
                )
                for node in row["nodes"]
            ),
            "edges": tuple(
                EducationalGraphEdge(**{**edge, "kind": GraphEdgeKind(edge["kind"])})
                for edge in row["edges"]
            ),
            "claim_ids": tuple(row["claim_ids"]),
            "evidence_hashes": tuple(row["evidence_hashes"]),
            "source_hashes": tuple(row["source_hashes"]),
            "derivation_hashes": tuple(row["derivation_hashes"]),
        }
    )


def spec_from_dict(row: dict[str, Any]) -> ExerciseSpec:
    _exact(row, set(ExerciseSpec.__dataclass_fields__))
    return ExerciseSpec(
        **{
            **row,
            "family": ExerciseFamily(row["family"]),
            "learning_objectives": tuple(row["learning_objectives"]),
            "required_concepts": tuple(row["required_concepts"]),
            "accepted_answer_type": StudentAnswerKind(row["accepted_answer_type"]),
            "allowed_units": tuple(row["allowed_units"]),
            "hint_ladder": tuple(row["hint_ladder"]),
            "template_ids_ru": tuple(row["template_ids_ru"]),
            "template_ids_en": tuple(row["template_ids_en"]),
        }
    )


def instance_from_dict(row: dict[str, Any]) -> ExerciseInstance:
    _exact(row, set(ExerciseInstance.__dataclass_fields__))
    return ExerciseInstance(
        **{
            **row,
            "accepted_equivalent_forms": tuple(row["accepted_equivalent_forms"]),
            "provenance_dependencies": tuple(row["provenance_dependencies"]),
            "split_memberships": tuple(
                tuple(item) for item in row["split_memberships"]
            ),
            "counterfactuals": tuple(
                CounterfactualAnswer(
                    **{
                        **item,
                        "diagnosis": MisconceptionCode(item["diagnosis"]),
                        "matching_node_ids": tuple(item["matching_node_ids"]),
                    }
                )
                for item in row["counterfactuals"]
            ),
        }
    )


def presented_from_dict(row: dict[str, Any]) -> PresentedExercise:
    _exact(row, set(PresentedExercise.__dataclass_fields__))
    return PresentedExercise(
        **{**row, "learning_objectives": tuple(row["learning_objectives"])}
    )


def compilation_receipt_from_dict(
    row: dict[str, Any],
) -> EducationalCompilationReceipt:
    _exact(row, set(EducationalCompilationReceipt.__dataclass_fields__))
    return EducationalCompilationReceipt(
        **{
            **row,
            "actor_identity_type": ActorIdentityType(row["actor_identity_type"]),
        }
    )


def explanation_plan_from_dict(row: dict[str, Any]) -> ExplanationPlan:
    _exact(row, set(ExplanationPlan.__dataclass_fields__))
    return ExplanationPlan(
        **{
            **row,
            "mode": ExplanationMode(row["mode"]),
            "segments": tuple(
                ExplanationSegment(
                    **{
                        **item,
                        "kind": ExplanationSegmentKind(item["kind"]),
                        "node_ids": tuple(item["node_ids"]),
                        "permitted_fields": tuple(item["permitted_fields"]),
                    }
                )
                for item in row["segments"]
            ),
        }
    )


def explanation_from_dict(row: dict[str, Any]) -> ExplanationArtifact:
    _exact(row, set(ExplanationArtifact.__dataclass_fields__))
    return ExplanationArtifact(
        **{
            **row,
            "mode": ExplanationMode(row["mode"]),
            "numeric_node_ids": tuple(row["numeric_node_ids"]),
            "formula_node_ids": tuple(row["formula_node_ids"]),
            "source_node_ids": tuple(row["source_node_ids"]),
        }
    )


def student_answer_from_dict(row: dict[str, Any]) -> StudentAnswer:
    _exact(row, set(StudentAnswer.__dataclass_fields__))
    return StudentAnswer(
        **{
            **row,
            "answer_kind": StudentAnswerKind(row["answer_kind"]),
            "parse_status": AnswerParseStatus(row["parse_status"]),
            "issues": tuple(row["issues"]),
        }
    )


def diagnosis_from_dict(row: dict[str, Any]) -> ErrorDiagnosis:
    _exact(row, set(ErrorDiagnosis.__dataclass_fields__))
    return ErrorDiagnosis(
        **{
            **row,
            "code": MisconceptionCode(row["code"]),
            "confidence": DiagnosisConfidence(row["confidence"]),
            "matching_node_ids": tuple(row["matching_node_ids"]),
        }
    )


def grading_from_dict(row: dict[str, Any]) -> GradingResult:
    _exact(row, set(GradingResult.__dataclass_fields__))
    return GradingResult(
        **{
            **row,
            "parse_status": AnswerParseStatus(row["parse_status"]),
            "correctness_status": GradingStatus(row["correctness_status"]),
            "correct_nodes": tuple(row["correct_nodes"]),
            "incorrect_nodes": tuple(row["incorrect_nodes"]),
            "error_diagnoses": tuple(
                diagnosis_from_dict(item) for item in row["error_diagnoses"]
            ),
        }
    )


def hint_from_dict(row: dict[str, Any]) -> HintArtifact:
    _exact(row, set(HintArtifact.__dataclass_fields__))
    return HintArtifact(
        **{
            **row,
            "level": HintLevel(row["level"]),
            "revealed_node_ids": tuple(row["revealed_node_ids"]),
            "diagnosis_codes": tuple(
                MisconceptionCode(item) for item in row["diagnosis_codes"]
            ),
            "diagnosis_hashes": tuple(row["diagnosis_hashes"]),
        }
    )


def hint_plan_from_dict(row: dict[str, Any]) -> HintPlan:
    _exact(row, set(HintPlan.__dataclass_fields__))
    return HintPlan(
        **{
            **row,
            "node_order": tuple(row["node_order"]),
            "diagnosis_hashes": tuple(row["diagnosis_hashes"]),
        }
    )


def event_from_dict(row: dict[str, Any]) -> TutorEvent:
    row.setdefault("operation_id", None)
    _exact(row, set(TutorEvent.__dataclass_fields__))
    return TutorEvent(**row)


def session_from_dict(row: dict[str, Any]) -> TutorSession:
    _exact(row, set(TutorSession.__dataclass_fields__))
    return TutorSession(
        **{
            **row,
            "attempt_hashes": tuple(row["attempt_hashes"]),
            "grading_result_hashes": tuple(row["grading_result_hashes"]),
            "hint_hashes": tuple(row["hint_hashes"]),
            "status": TutorSessionStatus(row["status"]),
            "domain_dependencies": tuple(row["domain_dependencies"]),
        }
    )


def _exact(row: dict[str, Any], fields: set[str]) -> None:
    if not isinstance(row, dict) or set(row) != fields:
        raise ValueError("educational artifact has an invalid schema")
