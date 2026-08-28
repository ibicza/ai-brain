"""Immutable content-addressed exercise specifications."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.education.models import (
    ExerciseFamily,
    ExerciseSpec,
    StudentAnswerKind,
)
from ai_brain.stage2.education.version import EXERCISE_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import content_hash


def make_exercise_spec(
    exercise_id: str,
    family: ExerciseFamily,
    domain_version: str,
    difficulty_tier: int,
    *,
    learning_objectives: tuple[str, ...],
    required_concepts: tuple[str, ...],
    parameter_constraints: dict[str, Any],
    accepted_answer_type: StudentAnswerKind,
    allowed_units: tuple[str, ...] = (),
    template_ids_ru: tuple[str, ...] = ("ru.v1",),
    template_ids_en: tuple[str, ...] = ("en.v1",),
) -> ExerciseSpec:
    if not 0 <= difficulty_tier <= 5:
        raise ValueError("exercise difficulty must be in 0..5")
    body = {
        "exercise_id": exercise_id,
        "family": family,
        "domain_version": domain_version,
        "difficulty_tier": difficulty_tier,
        "learning_objectives": learning_objectives,
        "required_concepts": required_concepts,
        "parameter_constraints": parameter_constraints,
        "accepted_answer_type": accepted_answer_type,
        "allowed_units": allowed_units,
        "grading_policy": "EXACT_DECIMAL_TYPED_UNITS_V1",
        "hint_ladder": (1, 2, 3, 4, 5),
        "template_ids_ru": template_ids_ru,
        "template_ids_en": template_ids_en,
        "source_policy": "ACTIVE_CONFLICT_FREE_CHEMISTRY_V4",
        "schema_version": EXERCISE_SCHEMA_VERSION,
    }
    return ExerciseSpec(**body, spec_hash=content_hash(body))


def verify_exercise_spec(spec: ExerciseSpec) -> None:
    body = asdict(spec)
    digest = body.pop("spec_hash")
    if content_hash(body) != digest:
        raise ValueError("exercise spec hash mismatch")
    if spec.schema_version != EXERCISE_SCHEMA_VERSION:
        raise ValueError("incompatible exercise schema")
    if tuple(spec.hint_ladder) != (1, 2, 3, 4, 5):
        raise ValueError("exercise spec lacks the complete hint ladder")
