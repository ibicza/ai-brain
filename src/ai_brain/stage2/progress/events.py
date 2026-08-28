"""Canonical construction and validation of observable progress events."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage2.progress.concepts import CONCEPTS
from ai_brain.stage2.progress.models import ProgressEvent, ProgressEventKind
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
    observed_at: str | None = None,
) -> ProgressEvent:
    if not learner_id or not conversation_id or not tutor_session_id:
        raise ValueError("progress event requires explicit identity bindings")
    if not concept_ids or not set(concept_ids) <= set(CONCEPTS):
        raise ValueError("progress event has invalid concept bindings")
    if (
        sequence < 1
        or hint_count < 0
        or (hint_level is not None and hint_level not in range(1, 6))
    ):
        raise ValueError("progress event has invalid bounded counters")
    if event_kind is ProgressEventKind.ANSWER_GRADED and not grading_result_hash:
        raise ValueError("graded progress requires the trusted grading result hash")
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
        "grading_result_hash": grading_result_hash,
        "correct": correct,
        "trusted_current": trusted_current,
        "hint_level": hint_level,
        "hint_count": hint_count,
        "solution_revealed": solution_revealed,
        "observed_at": observed_at or utc_now(),
        "previous_event_hash": previous_event_hash,
        "schema_version": LEARNER_PROGRESS_SCHEMA_VERSION,
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
