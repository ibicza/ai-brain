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
FIXTURE_SCHEMA_VERSION = 2


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
    fixture_ids = []
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        fixture = json.loads(line)
        body = dict(fixture)
        digest = body.pop("fixture_hash")
        if content_hash(body) != digest:
            raise ValueError("independent diagnosis fixture hash mismatch")
        if (
            fixture.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
            or fixture.get("human_review_status") != "NOT_REVIEWED"
            or not fixture.get("fixture_generator")
            or not fixture.get("construction_method")
            or "fixture_reviewer" in fixture
        ):
            raise ValueError("independent fixture provenance is misleading")
        if set(fixture["public_exercise"]) != PUBLIC_EXERCISE_FIELDS:
            raise ValueError("independent fixture public exercise leaks private data")
        fixture_ids.append(fixture["fixture_id"])
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
                build_hint_plan(
                    entry.internal_instance.instance_id,
                    entry.graph,
                    grading=grade,
                ),
                entry.graph,
                HintLevel.ORIENT,
                language="en",
                grading=grade,
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
    predicted_precisions = []
    recalls = []
    per_category = {}
    for category in categories:
        predictions = category_predictions[category]
        precision = category_correct[category] / predictions if predictions else None
        recall = category_correct[category] / category_totals[category]
        if precision is not None:
            predicted_precisions.append(precision)
        recalls.append(recall)
        per_category[category] = {
            "precision": precision,
            "recall": recall,
            "support": category_totals[category],
            "prediction_count": predictions,
            "correct_prediction_count": category_correct[category],
        }
    total_predictions = sum(category_predictions.values())
    total_correct = sum(category_correct.values())
    fixture_manifest = _fixture_manifest(tuple(fixture_ids))
    macro_precision = (
        sum(predicted_precisions) / len(predicted_precisions)
        if predicted_precisions
        else None
    )
    return {
        "evaluation_kind": "SYNTHETIC_CROSS_IMPLEMENTATION",
        "metric_formula_version": "m292-honest-abstention-v1",
        "fixture_count": count,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture_universe_hash": fixture_manifest["universe_hash"],
        "diagnosis_fixture_manifest": fixture_manifest,
        "exact_diagnosis_count": total_correct,
        "ambiguous_diagnosis_count": ambiguous,
        "unclassified_count": unclassified,
        "wrong_confident_diagnosis": wrong_confident,
        "grading_status_mismatch_count": grading_mismatch,
        "micro_precision": total_correct / total_predictions
        if total_predictions
        else None,
        "macro_precision": macro_precision,
        "macro_precision_predicted_categories": macro_precision,
        "macro_recall": sum(recalls) / len(recalls),
        "diagnosis_coverage": (count - unclassified) / count if count else 0.0,
        "abstention_rate": unclassified / count if count else 0.0,
        "per_category": per_category,
        "confusion_matrix": {
            key: dict(sorted(value.items())) for key, value in sorted(confusion.items())
        },
        "independently_tested_targeted_hints": tested_hints,
        "wrong_targeted_hints": wrong_targeted_hints,
    }


def _fixture_manifest(fixture_ids: tuple[str, ...]) -> dict:
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("duplicate independent fixture id")
    universe = tuple(sorted(fixture_ids))
    development = tuple(
        value for value in universe if int(content_hash(value)[:8], 16) % 5 != 0
    )
    final = tuple(value for value in universe if value not in set(development))
    intersection = len(set(development) & set(final))
    body = {
        "axis": "SYNTHETIC_DIAGNOSIS_FIXTURE_PARTITION",
        "axis_kind": "SYNTHETIC_EVALUATION_PARTITION",
        "universe_kind": "fixture_id",
        "universe_hash": content_hash(universe),
        "universe_count": len(universe),
        "development": development,
        "final_validation": final,
        "intersection_count": intersection,
    }
    if not development or not final or intersection:
        raise ValueError("invalid independent fixture partition")
    return {**body, "manifest_hash": content_hash(body)}
