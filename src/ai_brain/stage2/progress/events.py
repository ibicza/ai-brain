"""Canonical tagged construction of learner progress events v3."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage2.progress.models import (
    AnswerGradedFacts,
    HintUsedFacts,
    ObservationFacts,
    ProgressEvent,
    ProgressEventKind,
    SolutionRevealedFacts,
)
from ai_brain.stage2.progress.version import LEARNER_PROGRESS_SCHEMA_VERSION


def make_progress_event(
    *,
    learner_id: str,
    conversation_id: str,
    tutor_session_id: str,
    catalog_entry_hash: str,
    semantic_key_hash: str,
    concept_ids: tuple[str, ...],
    event_kind: ProgressEventKind,
    sequence: int,
    previous_event_hash: str | None,
    grading_result_hash: str | None = None,
    correct: bool | None = None,
    trusted_current: bool = True,
    hint_level: int | None = None,
    hint_count: int = 0,
    solution_revealed: bool = False,
    hint_hash: str | None = None,
    explanation_hash: str | None = None,
    observed_at: str | None = None,
    authority_hashes: tuple[str, ...] = (),
    operation_id: str | None = None,
) -> ProgressEvent:
    # hint_count/solution_revealed remain accepted only to make migration errors
    # explicit; they are never persisted in unrelated event payloads.
    del hint_count, solution_revealed
    if not learner_id or not conversation_id or not tutor_session_id:
        raise ValueError("progress event requires explicit identity bindings")
    if not concept_ids or any(
        not item
        or len(item) > 128
        or not item.replace("_", "").replace("-", "").replace(".", "").isalnum()
        for item in concept_ids
    ):
        raise ValueError("progress event has invalid concept bindings")
    if sequence < 1:
        raise ValueError("progress event has invalid sequence")
    if event_kind in {
        ProgressEventKind.ANSWER_GRADED,
        ProgressEventKind.EXERCISE_SOLVED,
    }:
        if not grading_result_hash or not isinstance(correct, bool):
            raise ValueError("graded progress requires exact grading facts")
        payload = AnswerGradedFacts(grading_result_hash, correct)
    elif event_kind is ProgressEventKind.HINT_USED:
        exact_hint = hint_hash or (
            authority_hashes[-1] if len(authority_hashes) > 1 else None
        )
        if not exact_hint or hint_level not in range(1, 6):
            raise ValueError("hint progress requires exact hint hash and level")
        payload = HintUsedFacts(exact_hint, hint_level)
    elif event_kind is ProgressEventKind.SOLUTION_REVEALED:
        exact_explanation = explanation_hash or (
            authority_hashes[-1] if len(authority_hashes) > 1 else None
        )
        if not exact_explanation:
            raise ValueError("solution progress requires exact explanation hash")
        payload = SolutionRevealedFacts(exact_explanation)
    else:
        payload = ObservationFacts(authority_hashes[-1] if authority_hashes else None)
    body = {
        "event_id": "",
        "sequence": sequence,
        "learner_id": learner_id,
        "conversation_id": conversation_id,
        "tutor_session_id": tutor_session_id,
        "catalog_entry_hash": catalog_entry_hash,
        "semantic_key_hash": semantic_key_hash,
        "concept_ids": tuple(dict.fromkeys(concept_ids)),
        "event_kind": event_kind,
        "payload": payload,
        "trusted_current": trusted_current,
        "observed_at": observed_at or utc_now(),
        "previous_event_hash": previous_event_hash,
        "schema_version": LEARNER_PROGRESS_SCHEMA_VERSION,
        "authority_hashes": authority_hashes,
        "operation_id": operation_id,
    }
    body["event_id"] = f"progress.event.{content_hash(body)[:24]}"
    return ProgressEvent(**body, event_hash=content_hash(body))


def verify_progress_event(event: ProgressEvent) -> None:
    body = asdict(event)
    digest = body.pop("event_hash")
    if (
        event.schema_version != LEARNER_PROGRESS_SCHEMA_VERSION
        or content_hash(body) != digest
    ):
        raise ValueError("progress event hash or schema mismatch")
    expected = {
        ProgressEventKind.ANSWER_GRADED: AnswerGradedFacts,
        ProgressEventKind.EXERCISE_SOLVED: AnswerGradedFacts,
        ProgressEventKind.HINT_USED: HintUsedFacts,
        ProgressEventKind.SOLUTION_REVEALED: SolutionRevealedFacts,
    }.get(event.event_kind, ObservationFacts)
    if not isinstance(event.payload, expected):
        raise TypeError("progress event kind and tagged payload disagree")
