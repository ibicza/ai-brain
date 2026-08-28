"""Independent fixture evaluation, separate from production counterfactual plumbing."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.hints import (
    GENERIC_ONLY,
    TARGETED_HINT_STRATEGIES,
    build_hint_plan,
    render_hint,
)
from ai_brain.stage2.education.models import (
    AnswerParseStatus,
    DiagnosisConfidence,
    HintLevel,
    MisconceptionCode,
    StudentAnswer,
)
from ai_brain.stage2.facts.canonical import content_hash

PUBLIC_EXERCISE_FIELDS = {
    "exercise_id",
    "language",
    "question_text",
    "structured_public_givens",
    "difficulty_metadata",
}


def evaluate_independent_fixtures(catalog, fixture_path: Path) -> dict:
    entries = {entry.semantic_key.semantic_key_hash: entry for entry in catalog.entries}
    confusion = defaultdict(Counter)
    category_totals = Counter()
    category_predictions = Counter()
    category_correct = Counter()
    wrong_confident = 0
    ambiguous = 0
    unclassified = 0
    grading_mismatch = 0
    tested_hints = 0
    wrong_targeted_hints = 0
    count = 0
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        fixture = json.loads(line)
        body = dict(fixture)
        digest = body.pop("fixture_hash")
        if content_hash(body) != digest:
            raise ValueError("independent diagnosis fixture hash mismatch")
        if set(fixture["public_exercise"]) != PUBLIC_EXERCISE_FIELDS:
            raise ValueError("independent fixture public exercise leaks private data")
        entry = entries[fixture["internal_fixture_binding"]]
        submitted = fixture["submitted_answer"]
        answer_body = {
            "answer_kind": entry.exercise_spec.accepted_answer_type,
            "raw_input_hash": content_hash(submitted),
            "interpreted_answer": submitted["interpreted_answer"],
            "parse_status": AnswerParseStatus.INVALID
            if submitted["interpreted_answer"] is None
            else AnswerParseStatus.PARSED,
            "issues": tuple(submitted["issues"]),
            "confirmed": True,
        }
        answer = StudentAnswer(**answer_body, answer_hash=content_hash(answer_body))
        grade = grade_answer(
            entry.internal_instance,
            answer,
            entry.graph,
            attempt_id=f"fixture.attempt.{digest[:24]}",
            created_at="2026-08-28T00:00:00Z",
        )
        if grade.correctness_status.value != fixture["expected_grading_status"]:
            grading_mismatch += 1
        supported = set(fixture["supported_diagnosis_set"])
        forbidden = set(fixture["forbidden_diagnosis_set"])
        predicted = {
            diagnosis.code.value
            for diagnosis in grade.error_diagnoses
            if diagnosis.code
            not in {
                MisconceptionCode.UNCLASSIFIED_ERROR,
                MisconceptionCode.AMBIGUOUS_DIAGNOSIS,
            }
        }
        label = (
            min(supported) if supported else MisconceptionCode.UNCLASSIFIED_ERROR.value
        )
        category_totals[label] += 1
        for value in predicted:
            category_predictions[value] += 1
            confusion[label][value] += 1
            if value in supported:
                category_correct[value] += 1
        if any(
            diagnosis.confidence == DiagnosisConfidence.EXACT_MATCH
            and diagnosis.code.value in forbidden
            for diagnosis in grade.error_diagnoses
        ):
            wrong_confident += 1
        if any(
            diagnosis.code == MisconceptionCode.AMBIGUOUS_DIAGNOSIS
            for diagnosis in grade.error_diagnoses
        ):
            ambiguous += 1
        if not predicted:
            unclassified += 1
        if grade.error_diagnoses:
            render_hint(
                build_hint_plan(entry.internal_instance.instance_id, entry.graph),
                entry.graph,
                HintLevel.ORIENT,
                language="en",
                diagnoses=grade.error_diagnoses,
            )
            if any(
                item.confidence == DiagnosisConfidence.EXACT_MATCH
                and TARGETED_HINT_STRATEGIES[item.code] != GENERIC_ONLY
                for item in grade.error_diagnoses
            ):
                tested_hints += 1
            if any(
                item.confidence == DiagnosisConfidence.EXACT_MATCH
                and TARGETED_HINT_STRATEGIES[item.code] != GENERIC_ONLY
                and item.code.value in forbidden
                for item in grade.error_diagnoses
            ):
                wrong_targeted_hints += 1
        count += 1
    categories = sorted(category_totals)
    precisions = []
    recalls = []
    per_category = {}
    for category in categories:
        precision = (
            category_correct[category] / category_predictions[category]
            if category_predictions[category]
            else 1.0
        )
        recall = category_correct[category] / category_totals[category]
        precisions.append(precision)
        recalls.append(recall)
        per_category[category] = {
            "precision": precision,
            "recall": recall,
            "support": category_totals[category],
        }
    return {
        "fixture_count": count,
        "exact_diagnosis_count": sum(
            category_correct[category] for category in categories
        ),
        "ambiguous_diagnosis_count": ambiguous,
        "unclassified_count": unclassified,
        "wrong_confident_diagnosis": wrong_confident,
        "grading_status_mismatch_count": grading_mismatch,
        "macro_precision": sum(precisions) / len(precisions),
        "macro_recall": sum(recalls) / len(recalls),
        "per_category": per_category,
        "confusion_matrix": {
            key: dict(sorted(value.items())) for key, value in sorted(confusion.items())
        },
        "independently_tested_targeted_hints": tested_hints,
        "wrong_targeted_hints": wrong_targeted_hints,
    }
