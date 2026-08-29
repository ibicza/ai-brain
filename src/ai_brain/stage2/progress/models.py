"""Immutable public and persisted progress models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProgressEventKind(StrEnum):
    EXERCISE_PRESENTED = "EXERCISE_PRESENTED"
    ANSWER_GRADED = "ANSWER_GRADED"
    HINT_USED = "HINT_USED"
    SOLUTION_REVEALED = "SOLUTION_REVEALED"
    EXERCISE_SOLVED = "EXERCISE_SOLVED"
    EXERCISE_ABANDONED = "EXERCISE_ABANDONED"
    CONCEPT_DEMONSTRATED = "CONCEPT_DEMONSTRATED"
    PROGRESS_RESET = "PROGRESS_RESET"


class ConceptProgressStatus(StrEnum):
    NOT_SEEN = "NOT_SEEN"
    PRACTICING = "PRACTICING"
    DEMONSTRATED = "DEMONSTRATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class RecommendationReason(StrEnum):
    NEEDS_REVIEW_AFTER_ERRORS = "NEEDS_REVIEW_AFTER_ERRORS"
    CONTINUE_PRACTICE = "CONTINUE_PRACTICE"
    NEXT_PREREQUISITE_READY = "NEXT_PREREQUISITE_READY"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"


@dataclass(frozen=True)
class AnswerGradedFacts:
    grading_result_hash: str
    correct: bool


@dataclass(frozen=True)
class HintUsedFacts:
    hint_hash: str
    level: int


@dataclass(frozen=True)
class SolutionRevealedFacts:
    explanation_hash: str


@dataclass(frozen=True)
class ObservationFacts:
    authority_artifact_hash: str | None = None


type ProgressEventPayload = (
    AnswerGradedFacts | HintUsedFacts | SolutionRevealedFacts | ObservationFacts
)


@dataclass(frozen=True)
class ProgressEvent:
    event_id: str
    sequence: int
    learner_id: str
    conversation_id: str
    tutor_session_id: str
    catalog_entry_hash: str
    semantic_key_hash: str
    concept_ids: tuple[str, ...]
    event_kind: ProgressEventKind
    payload: ProgressEventPayload
    trusted_current: bool
    observed_at: str
    previous_event_hash: str | None
    schema_version: int
    event_hash: str
    authority_hashes: tuple[str, ...] = ()
    operation_id: str | None = None

    @property
    def grading_result_hash(self) -> str | None:
        return (
            self.payload.grading_result_hash
            if isinstance(self.payload, AnswerGradedFacts)
            else None
        )

    @property
    def correct(self) -> bool | None:
        return (
            self.payload.correct
            if isinstance(self.payload, AnswerGradedFacts)
            else None
        )

    @property
    def hint_level(self) -> int | None:
        return self.payload.level if isinstance(self.payload, HintUsedFacts) else None

    @property
    def hint_count(self) -> int:
        return int(isinstance(self.payload, HintUsedFacts))

    @property
    def solution_revealed(self) -> bool:
        return isinstance(self.payload, SolutionRevealedFacts)


@dataclass(frozen=True)
class ConceptProgressProjection:
    learner_id: str
    concept_id: str
    status: ConceptProgressStatus
    qualifying_attempt_count: int
    correct_count: int
    incorrect_count: int
    correct_without_hint_count: int
    hints_used: int
    solutions_revealed: int
    distinct_semantic_keys_attempted: tuple[str, ...]
    last_attempted: str | None
    last_demonstrated: str | None
    evidence_event_hashes: tuple[str, ...]
    policy_version: str
    projection_hash: str


@dataclass(frozen=True)
class ExerciseRecommendation:
    learner_id: str
    recommended_concept: str
    prerequisite_state: tuple[tuple[str, str], ...]
    candidate_catalog_entry_hashes: tuple[str, ...]
    selected_entry_hash: str
    reason_code: RecommendationReason
    evidence_summary: str
    generated_at: str
    recommendation_hash: str


@dataclass(frozen=True)
class PublicProgressSummary:
    concepts_attempted: int
    concepts_demonstrated: int
    concepts_needing_review: int
    attempts: int
    successful_attempts: int
    hints_used: int
    solutions_revealed: int
    suggested_next_concept: str | None
    suggestion_reason: str | None
    history_status: str = "PROGRESS_HISTORY_VALID"
    current_authority_status: str = "PROGRESS_CURRENT_AUTHORITY"
