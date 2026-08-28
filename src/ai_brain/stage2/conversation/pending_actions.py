"""Opaque, single-use pending actions bound to exact context and dependencies."""

from __future__ import annotations

import secrets
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

from ai_brain.stage2.conversation.models import (
    ConversationState,
    PendingAction,
    PendingActionStatus,
    PublicPendingAction,
)
from ai_brain.stage2.conversation.version import PENDING_ACTION_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import content_hash, utc_now


def prepare_pending_action(
    *,
    learner_id: str,
    conversation_id: str,
    action_kind: str,
    request_hash: str,
    language: str,
    payload: dict,
    dependency_snapshot: tuple[str, ...],
    previous_state: ConversationState,
    ttl_seconds: int = 300,
    created_at: str | None = None,
) -> PendingAction:
    if ttl_seconds < 1 or ttl_seconds > 900:
        raise ValueError("pending action expiry is outside the bounded policy")
    timestamp = created_at or utc_now()
    expires = (
        (datetime.fromisoformat(timestamp) + timedelta(seconds=ttl_seconds))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )
    body = {
        "pending_id": "pending_" + secrets.token_urlsafe(24),
        "learner_id": learner_id,
        "conversation_id": conversation_id,
        "action_kind": action_kind,
        "request_hash": request_hash,
        "language": language,
        "payload": payload,
        "dependency_snapshot": dependency_snapshot,
        "previous_state": previous_state,
        "created_at": timestamp,
        "expires_at": expires,
        "status": PendingActionStatus.PREPARED,
        "schema_version": PENDING_ACTION_SCHEMA_VERSION,
    }
    return PendingAction(**body, pending_hash=content_hash(body))


def verify_pending(action: PendingAction) -> None:
    body = asdict(action)
    digest = body.pop("pending_hash")
    if (
        action.schema_version != PENDING_ACTION_SCHEMA_VERSION
        or content_hash(body) != digest
    ):
        raise ValueError("pending action hash or schema mismatch")


def authorize_pending(
    action: PendingAction,
    *,
    learner_id: str,
    conversation_id: str,
    language: str,
    dependency_snapshot: tuple[str, ...],
    now: str | None = None,
) -> PendingAction:
    verify_pending(action)
    if action.status is not PendingActionStatus.PREPARED:
        raise ValueError("pending action is not executable")
    if (
        action.learner_id != learner_id
        or action.conversation_id != conversation_id
        or action.language != language
    ):
        raise ValueError("pending action context mismatch")
    timestamp = now or utc_now()
    if datetime.fromisoformat(timestamp) >= datetime.fromisoformat(action.expires_at):
        raise ValueError("pending action expired")
    if action.dependency_snapshot != dependency_snapshot:
        raise ValueError("pending action dependencies changed")
    provisional = replace(action, status=PendingActionStatus.EXECUTED, pending_hash="")
    body = asdict(provisional)
    body.pop("pending_hash")
    return replace(provisional, pending_hash=content_hash(body))


def public_pending(action: PendingAction) -> PublicPendingAction:
    return PublicPendingAction(
        pending_id=action.pending_id,
        action_kind=action.action_kind,
        summary="Run the prepared trusted calculation"
        if action.language == "en"
        else "Выполнить подготовленный доверенный расчёт",
        expires_at=action.expires_at,
        confirmation_required=True,
    )
