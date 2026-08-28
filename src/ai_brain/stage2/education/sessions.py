"""Immutable event-sourced tutor session transitions."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.education.models import (
    ExerciseInstance,
    TutorEvent,
    TutorSession,
    TutorSessionStatus,
)
from ai_brain.stage2.education.version import TUTOR_SESSION_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import content_hash, utc_now

EVENT_TYPES = frozenset(
    {
        "SESSION_PRESENTED",
        "ANSWER_SUBMITTED",
        "ANSWER_GRADED",
        "HINT_ISSUED",
        "SOLUTION_REVEALED",
        "SESSION_ABANDONED",
    }
)

ALLOWED_EVENT_STATES = {
    "ANSWER_SUBMITTED": frozenset(
        {
            TutorSessionStatus.PRESENTED,
            TutorSessionStatus.ATTEMPTED,
            TutorSessionStatus.HINTED,
        }
    ),
    "ANSWER_GRADED": frozenset({TutorSessionStatus.ATTEMPTED}),
    "HINT_ISSUED": frozenset(
        {
            TutorSessionStatus.PRESENTED,
            TutorSessionStatus.ATTEMPTED,
            TutorSessionStatus.HINTED,
        }
    ),
    "SOLUTION_REVEALED": frozenset(
        {
            TutorSessionStatus.ATTEMPTED,
            TutorSessionStatus.HINTED,
            TutorSessionStatus.SOLVED,
        }
    ),
    "SESSION_ABANDONED": frozenset(
        {
            TutorSessionStatus.PRESENTED,
            TutorSessionStatus.ATTEMPTED,
            TutorSessionStatus.HINTED,
        }
    ),
}


def start_session(
    instance: ExerciseInstance,
    *,
    session_id: str,
    created_at: str | None = None,
) -> tuple[TutorSession, TutorEvent]:
    timestamp = created_at or utc_now()
    event = make_event(
        session_id,
        sequence=1,
        event_type="SESSION_PRESENTED",
        payload={
            "exercise_id": instance.instance_id,
            "exercise_hash": instance.instance_hash,
        },
        previous_event_hash=None,
        created_at=timestamp,
    )
    body = {
        "session_id": session_id,
        "exercise_id": instance.instance_id,
        "exercise_hash": instance.instance_hash,
        "language": instance.language,
        "attempt_hashes": (),
        "grading_result_hashes": (),
        "hint_hashes": (),
        "status": TutorSessionStatus.PRESENTED,
        "graph_hash": instance.hidden_answer_graph_hash,
        "catalog_entry_hash": instance.catalog_entry_hash,
        "domain_dependencies": instance.provenance_dependencies,
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_event_hash": event.event_hash,
        "schema_version": TUTOR_SESSION_SCHEMA_VERSION,
    }
    return TutorSession(**body, session_hash=content_hash(body)), event


def make_event(
    session_id: str,
    *,
    sequence: int,
    event_type: str,
    payload: dict[str, Any],
    previous_event_hash: str | None,
    created_at: str | None = None,
) -> TutorEvent:
    if event_type not in EVENT_TYPES or sequence < 1:
        raise ValueError("invalid tutor event")
    body = {
        "event_id": "",
        "session_id": session_id,
        "sequence": sequence,
        "event_type": event_type,
        "payload": payload,
        "previous_event_hash": previous_event_hash,
        "created_at": created_at or utc_now(),
    }
    body["event_id"] = f"education.event.{content_hash(body)[:24]}"
    return TutorEvent(**body, event_hash=content_hash(body))


def apply_event(session: TutorSession, event: TutorEvent) -> TutorSession:
    verify_session_hash(session)
    verify_event_hash(event)
    if (
        event.session_id != session.session_id
        or event.previous_event_hash != session.last_event_hash
    ):
        raise ValueError("tutor event chain mismatch")
    allowed = ALLOWED_EVENT_STATES.get(event.event_type)
    if allowed is None or session.status not in allowed:
        raise ValueError("invalid tutor session state transition")
    attempts = session.attempt_hashes
    grades = session.grading_result_hashes
    hints = session.hint_hashes
    status = session.status
    if event.event_type == "ANSWER_SUBMITTED":
        attempts = (*attempts, _required_hash(event.payload, "student_answer_hash"))
        status = TutorSessionStatus.ATTEMPTED
    elif event.event_type == "ANSWER_GRADED":
        if len(grades) >= len(attempts):
            raise ValueError("duplicate or unordered answer grade")
        grades = (*grades, _required_hash(event.payload, "grading_result_hash"))
        if event.payload.get("solved") is True:
            status = TutorSessionStatus.SOLVED
    elif event.event_type == "HINT_ISSUED":
        hints = (*hints, _required_hash(event.payload, "hint_hash"))
        status = TutorSessionStatus.HINTED
    elif event.event_type == "SOLUTION_REVEALED":
        status = TutorSessionStatus.SOLUTION_REVEALED
    elif event.event_type == "SESSION_ABANDONED":
        status = TutorSessionStatus.ABANDONED
    else:
        raise ValueError("SESSION_PRESENTED cannot be applied twice")
    body = {
        **asdict(session),
        "attempt_hashes": attempts,
        "grading_result_hashes": grades,
        "hint_hashes": hints,
        "status": status,
        "updated_at": event.created_at,
        "last_event_hash": event.event_hash,
    }
    body.pop("session_hash")
    return TutorSession(**body, session_hash=content_hash(body))


def verify_session_hash(session: TutorSession) -> None:
    body = asdict(session)
    digest = body.pop("session_hash")
    if content_hash(body) != digest:
        raise ValueError("tutor session hash mismatch")
    if session.schema_version != TUTOR_SESSION_SCHEMA_VERSION:
        raise ValueError("incompatible tutor session schema")


def verify_event_hash(event: TutorEvent) -> None:
    body = asdict(event)
    digest = body.pop("event_hash")
    if content_hash(body) != digest:
        raise ValueError("tutor event hash mismatch")
    if event.event_type not in EVENT_TYPES or event.sequence < 1:
        raise ValueError("invalid tutor event")


def _required_hash(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"tutor event lacks {key}")
    return value
