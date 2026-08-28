"""Evidence-bound misconception diagnosis without claims about learner intent."""

from __future__ import annotations

from typing import Any

from ai_brain.stage2.education.answers import numeric_equivalent, parse_unit
from ai_brain.stage2.education.models import (
    DiagnosisConfidence,
    ErrorDiagnosis,
    ExerciseInstance,
    MisconceptionCode,
    StudentAnswer,
)
from ai_brain.stage2.facts.canonical import content_hash


def diagnose_answer(
    instance: ExerciseInstance, answer: StudentAnswer
) -> tuple[ErrorDiagnosis, ...]:
    if answer.interpreted_answer is None:
        codes = _parse_issue_codes(answer.issues)
        return tuple(_make(code, DiagnosisConfidence.EXACT_MATCH) for code in codes)
    actual = answer.interpreted_answer
    matches = []
    for candidate in instance.counterfactuals:
        if _answers_match(actual, candidate.answer):
            matches.append(candidate)
    if len(matches) == 1:
        item = matches[0]
        return (
            _make(
                item.diagnosis,
                DiagnosisConfidence.EXACT_MATCH,
                value=item.answer,
                node_ids=item.matching_node_ids,
            ),
        )
    if len(matches) > 1:
        names = ", ".join(sorted(item.diagnosis.value for item in matches))
        return (
            _make(
                MisconceptionCode.AMBIGUOUS_DIAGNOSIS,
                DiagnosisConfidence.AMBIGUOUS,
                value=actual,
                node_ids=tuple(
                    sorted(
                        {node for item in matches for node in item.matching_node_ids}
                    )
                ),
                clarification=f"Which step produced this value? Candidates: {names}",
            ),
        )
    expected = instance.hidden_expected_answer
    if "unit" in actual and "unit" in expected:
        try:
            if (
                parse_unit(actual["unit"]).dimension
                != parse_unit(expected["unit"]).dimension
            ):
                return (
                    _make(
                        MisconceptionCode.UNIT_WRONG_DIMENSION,
                        DiagnosisConfidence.EXACT_MATCH,
                    ),
                )
        except ValueError:
            pass
    if "element_counts" in actual and "element_counts" in expected:
        return (
            _make(
                MisconceptionCode.ELEMENT_COUNT_WRONG, DiagnosisConfidence.PARTIAL_MATCH
            ),
        )
    return (
        _make(MisconceptionCode.UNCLASSIFIED_ERROR, DiagnosisConfidence.PARTIAL_MATCH),
    )


def _answers_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if {"value", "unit"} <= left.keys() and {"value", "unit"} <= right.keys():
        try:
            return numeric_equivalent(
                left["value"], left["unit"], right["value"], right["unit"]
            )[0]
        except (TypeError, ValueError):
            return False
    return left == right


def _parse_issue_codes(issues: tuple[str, ...]) -> tuple[MisconceptionCode, ...]:
    joined = " ".join(issues).casefold()
    if "unit" in joined:
        return (MisconceptionCode.UNIT_MISSING,)
    if "symbol" in joined:
        return (MisconceptionCode.UNKNOWN_ELEMENT_SYMBOL,)
    if "formula" in joined:
        return (MisconceptionCode.FORMULA_PARSE_ERROR,)
    return (MisconceptionCode.UNCLASSIFIED_ERROR,)


def _make(
    code: MisconceptionCode,
    confidence: DiagnosisConfidence,
    *,
    value: dict[str, Any] | None = None,
    node_ids: tuple[str, ...] = (),
    clarification: str | None = None,
) -> ErrorDiagnosis:
    body = {
        "code": code,
        "confidence": confidence,
        "counterfactual_value": value,
        "matching_node_ids": node_ids,
        "clarification": clarification,
    }
    return ErrorDiagnosis(**body, diagnosis_hash=content_hash(body))
