"""Immutable conversation, pending-action, replay, and public models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ConversationState(StrEnum):
    IDLE = "IDLE"
    EXERCISE_ACTIVE = "EXERCISE_ACTIVE"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class Speaker(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class ConversationIntent(StrEnum):
    START_TUTORING = "START_TUTORING"
    REQUEST_EXERCISE = "REQUEST_EXERCISE"
    SUBMIT_ANSWER = "SUBMIT_ANSWER"
    REQUEST_HINT = "REQUEST_HINT"
    REQUEST_SOLUTION = "REQUEST_SOLUTION"
    REQUEST_EXPLANATION = "REQUEST_EXPLANATION"
    REQUEST_FACT = "REQUEST_FACT"
    REQUEST_PROGRESS = "REQUEST_PROGRESS"
    REQUEST_NEXT_EXERCISE = "REQUEST_NEXT_EXERCISE"
    CHANGE_LANGUAGE = "CHANGE_LANGUAGE"
    CONFIRM_PENDING_ACTION = "CONFIRM_PENDING_ACTION"
    CANCEL_PENDING_ACTION = "CANCEL_PENDING_ACTION"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    END_CONVERSATION = "END_CONVERSATION"
    CLARIFY = "CLARIFY"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    COMPOSITE_REQUIRED = "COMPOSITE_REQUIRED"


class PendingActionStatus(StrEnum):
    PREPARED = "PREPARED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    STALE = "STALE"


class ConversationReplayStatus(StrEnum):
    CURRENT = "CURRENT"
    HISTORY_VALID_BUT_STALE = "HISTORY_VALID_BUT_STALE"
    STALE_EDUCATIONAL_SESSION = "STALE_EDUCATIONAL_SESSION"
    STALE_CATALOG = "STALE_CATALOG"
    STALE_FACT_MEMORY = "STALE_FACT_MEMORY"
    STALE_SOURCE_CHAIN = "STALE_SOURCE_CHAIN"
    STALE_TOOL = "STALE_TOOL"
    STALE_PENDING_ACTION = "STALE_PENDING_ACTION"
    INVALID_CONVERSATION = "INVALID_CONVERSATION"
    INVALID_TURN_CHAIN = "INVALID_TURN_CHAIN"
    INVALID_PROGRESS_EVENT = "INVALID_PROGRESS_EVENT"
    INVALID_PUBLIC_RESPONSE = "INVALID_PUBLIC_RESPONSE"


@dataclass(frozen=True)
class ParsedIntent:
    intent: ConversationIntent
    language: str
    payload: dict[str, Any]
    evidence: tuple[str, ...]
    parser_version: str
    intent_hash: str


@dataclass(frozen=True)
class TutorConversation:
    conversation_id: str
    learner_id: str
    language: str
    state: ConversationState
    previous_active_state: ConversationState
    active_tutor_session_id: str | None
    pending_action_id: str | None
    pending_clarification_id: str | None
    turn_hashes: tuple[str, ...]
    created_at: str
    updated_at: str
    last_event_hash: str | None
    schema_version: int
    conversation_hash: str


@dataclass(frozen=True)
class ConversationTurn:
    turn_id: str
    conversation_id: str
    sequence: int
    speaker: Speaker
    original_text_hash: str
    parsed_intent: ConversationIntent
    public_response_hash: str
    previous_turn_hash: str | None
    created_at: str
    turn_hash: str


@dataclass(frozen=True)
class PendingAction:
    pending_id: str
    learner_id: str
    conversation_id: str
    action_kind: str
    request_hash: str
    language: str
    payload: dict[str, Any]
    dependency_snapshot: tuple[str, ...]
    previous_state: ConversationState
    created_at: str
    expires_at: str
    status: PendingActionStatus
    schema_version: int
    pending_hash: str


@dataclass(frozen=True)
class PublicPendingAction:
    pending_id: str
    action_kind: str
    summary: str
    expires_at: str
    confirmation_required: bool


@dataclass(frozen=True)
class PublicConversationResponse:
    conversation_id: str
    conversation_state: str
    language: str
    response_kind: str
    text: str
    exercise: Any | None = None
    submission: Any | None = None
    hint: Any | None = None
    solution: Any | None = None
    progress: Any | None = None
    prepared_action: PublicPendingAction | None = None
    clarification_prompt: str | None = None


@dataclass(frozen=True)
class ConversationReplayResult:
    conversation_id: str
    status: ConversationReplayStatus
    state: str | None
    turn_count: int
    current_authority_status: str
