"""Public progress rendering without learner-trait inference."""

from ai_brain.stage2.progress.models import ConceptProgressStatus, PublicProgressSummary


def render_progress_summary(projections, recommendation=None) -> PublicProgressSummary:
    attempted = tuple(
        item
        for item in projections
        if item.status is not ConceptProgressStatus.NOT_SEEN
    )
    return PublicProgressSummary(
        concepts_attempted=len(attempted),
        concepts_demonstrated=sum(
            item.status is ConceptProgressStatus.DEMONSTRATED for item in projections
        ),
        concepts_needing_review=sum(
            item.status is ConceptProgressStatus.NEEDS_REVIEW for item in projections
        ),
        attempts=sum(item.correct_count + item.incorrect_count for item in attempted),
        successful_attempts=sum(item.correct_count for item in attempted),
        hints_used=sum(item.hints_used for item in attempted),
        solutions_revealed=sum(item.solutions_revealed for item in attempted),
        suggested_next_concept=recommendation.recommended_concept
        if recommendation
        else None,
        suggestion_reason=recommendation.reason_code.value if recommendation else None,
    )
