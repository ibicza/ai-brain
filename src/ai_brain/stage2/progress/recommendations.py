"""Deterministic, explainable curriculum recommendation."""

from __future__ import annotations

from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage2.progress.concepts import CONCEPTS, PREREQUISITES
from ai_brain.stage2.progress.models import (
    ConceptProgressProjection,
    ConceptProgressStatus,
    ExerciseRecommendation,
    RecommendationReason,
)


def recommend_exercise(
    learner_id: str,
    projections: tuple[ConceptProgressProjection, ...],
    candidates: dict[str, tuple[tuple[str, str], ...]],
    *,
    recent_semantic_key: str | None = None,
    review_requested: bool = False,
    generated_at: str | None = None,
) -> ExerciseRecommendation:
    by_concept = {item.concept_id: item for item in projections}
    selected_concept = None
    reason = None
    for status, code in (
        (
            ConceptProgressStatus.NEEDS_REVIEW,
            RecommendationReason.NEEDS_REVIEW_AFTER_ERRORS,
        ),
        (ConceptProgressStatus.PRACTICING, RecommendationReason.CONTINUE_PRACTICE),
    ):
        selected_concept = next(
            (
                c
                for c in CONCEPTS
                if by_concept[c].status is status and candidates.get(c)
            ),
            None,
        )
        if selected_concept:
            reason = code
            break
    if selected_concept is None:
        selected_concept = next(
            (
                c
                for c in CONCEPTS
                if by_concept[c].status is ConceptProgressStatus.NOT_SEEN
                and candidates.get(c)
                and all(
                    by_concept[p].status is ConceptProgressStatus.DEMONSTRATED
                    for p in PREREQUISITES.get(c, ())
                )
            ),
            None,
        )
        reason = RecommendationReason.NEXT_PREREQUISITE_READY
    if selected_concept is None and review_requested:
        selected_concept = next(
            (
                c
                for c in CONCEPTS
                if by_concept[c].status is ConceptProgressStatus.DEMONSTRATED
                and candidates.get(c)
            ),
            None,
        )
        reason = RecommendationReason.REVIEW_REQUESTED
    if selected_concept is None:
        raise ValueError("no current prerequisite-satisfied catalog candidate")
    available = tuple(
        item for item in candidates[selected_concept] if item[1] != recent_semantic_key
    )
    if not available:
        available = candidates[selected_concept]
    hashes = tuple(item[0] for item in available)
    prerequisite_state = tuple(
        (p, by_concept[p].status.value) for p in PREREQUISITES.get(selected_concept, ())
    )
    body = {
        "learner_id": learner_id,
        "recommended_concept": selected_concept,
        "prerequisite_state": prerequisite_state,
        "candidate_catalog_entry_hashes": hashes,
        "selected_entry_hash": hashes[0],
        "reason_code": reason,
        "evidence_summary": f"{by_concept[selected_concept].status.value}:{by_concept[selected_concept].qualifying_attempt_count}",
        "generated_at": generated_at or utc_now(),
    }
    return ExerciseRecommendation(**body, recommendation_hash=content_hash(body))
