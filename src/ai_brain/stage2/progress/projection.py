"""Transparent v1 progress projection from append-only observations."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.progress.events import verify_progress_event
from ai_brain.stage2.progress.models import (
    ConceptProgressProjection,
    ConceptProgressStatus,
    ProgressEvent,
    ProgressEventKind,
)
from ai_brain.stage2.progress.version import PROGRESS_POLICY_VERSION


def project_progress(
    learner_id: str,
    events: tuple[ProgressEvent, ...],
    *,
    concept_ids: tuple[str, ...] | None = None,
) -> tuple[ConceptProgressProjection, ...]:
    relevant: list[ProgressEvent] = []
    previous = None
    expected_sequence = 1
    for event in events:
        verify_progress_event(event)
        if event.learner_id != learner_id:
            raise ValueError("cross-learner progress reference")
        if event.sequence != expected_sequence or event.previous_event_hash != previous:
            raise ValueError("invalid progress event chain")
        expected_sequence += 1
        previous = event.event_hash
        if event.event_kind is ProgressEventKind.PROGRESS_RESET:
            relevant.clear()
        else:
            relevant.append(event)
    concepts = concept_ids
    if concepts is None:
        concepts = tuple(
            dict.fromkeys(concept for event in events for concept in event.concept_ids)
        )
    if len(set(concepts)) != len(concepts):
        raise ValueError("projection requires unique concepts")
    return tuple(
        _project_concept(learner_id, concept, relevant) for concept in concepts
    )


def _project_concept(
    learner_id: str, concept: str, events: list[ProgressEvent]
) -> ConceptProgressProjection:
    evidence = [e for e in events if concept in e.concept_ids]
    graded = [
        e
        for e in evidence
        if e.event_kind is ProgressEventKind.ANSWER_GRADED and e.trusted_current
    ]
    correct = [e for e in graded if e.correct is True]
    incorrect = [e for e in graded if e.correct is False]
    qualifying = [e for e in correct if not e.solution_revealed and e.hint_count <= 1]
    demonstrated_at = None
    distinct: list[str] = []
    for event in qualifying:
        if event.semantic_key_hash not in distinct:
            distinct.append(event.semantic_key_hash)
        if len(distinct) >= 2:
            demonstrated_at = event.observed_at
            break
    status = ConceptProgressStatus.NOT_SEEN
    if graded:
        status = ConceptProgressStatus.PRACTICING
    if demonstrated_at is not None:
        status = ConceptProgressStatus.DEMONSTRATED
        later_bad = {
            e.semantic_key_hash for e in incorrect if e.observed_at > demonstrated_at
        }
        if len(later_bad) >= 2:
            status = ConceptProgressStatus.NEEDS_REVIEW
    body = {
        "learner_id": learner_id,
        "concept_id": concept,
        "status": status,
        "qualifying_attempt_count": len(qualifying),
        "correct_count": len(correct),
        "incorrect_count": len(incorrect),
        "correct_without_hint_count": sum(
            e.hint_count == 0 and not e.solution_revealed for e in correct
        ),
        "hints_used": sum(e.hint_count for e in evidence),
        "solutions_revealed": sum(e.solution_revealed for e in evidence),
        "distinct_semantic_keys_attempted": tuple(
            dict.fromkeys(e.semantic_key_hash for e in graded)
        ),
        "last_attempted": graded[-1].observed_at if graded else None,
        "last_demonstrated": demonstrated_at,
        "evidence_event_hashes": tuple(e.event_hash for e in evidence),
        "policy_version": PROGRESS_POLICY_VERSION,
    }
    return ConceptProgressProjection(**body, projection_hash=content_hash(body))


def verify_projection(projection: ConceptProgressProjection) -> None:
    body = asdict(projection)
    digest = body.pop("projection_hash")
    if (
        projection.policy_version != PROGRESS_POLICY_VERSION
        or content_hash(body) != digest
    ):
        raise ValueError("progress projection hash or policy mismatch")
