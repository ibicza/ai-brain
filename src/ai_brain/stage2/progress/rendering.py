"""Public progress rendering without learner-trait inference."""

from ai_brain.stage2.progress.models import (
    ConceptProgressStatus,
    ProgressEventKind,
    PublicProgressSummary,
)


def render_progress_summary(
    projections, recommendation=None, *, events=None, current_authority: bool = True
) -> PublicProgressSummary:
    attempted = tuple(
        item
        for item in projections
        if item.status is not ConceptProgressStatus.NOT_SEEN
    )
    graded = tuple(
        item
        for item in (events or ())
        if item.event_kind is ProgressEventKind.ANSWER_GRADED
    )
    return PublicProgressSummary(
        concepts_attempted=len(attempted),
        concepts_demonstrated=sum(
            item.status is ConceptProgressStatus.DEMONSTRATED for item in projections
        ),
        concepts_needing_review=sum(
            item.status is ConceptProgressStatus.NEEDS_REVIEW for item in projections
        ),
        attempts=len(graded)
        if events is not None
        else sum(item.correct_count + item.incorrect_count for item in attempted),
        successful_attempts=sum(item.correct is True for item in graded)
        if events is not None
        else sum(item.correct_count for item in attempted),
        hints_used=sum(
            item.event_kind is ProgressEventKind.HINT_USED for item in events
        )
        if events is not None
        else sum(item.hints_used for item in attempted),
        solutions_revealed=sum(
            item.event_kind is ProgressEventKind.SOLUTION_REVEALED for item in events
        )
        if events is not None
        else sum(item.solutions_revealed for item in attempted),
        suggested_next_concept=recommendation.recommended_concept
        if recommendation
        else None,
        suggestion_reason=recommendation.reason_code.value if recommendation else None,
        history_status="PROGRESS_HISTORY_VALID",
        current_authority_status=(
            "PROGRESS_CURRENT_AUTHORITY"
            if current_authority
            else "PROGRESS_CURRENT_AUTHORITY_STALE"
        ),
    )
