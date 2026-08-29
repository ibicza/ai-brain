"""Typed reconstruction with separate history and current-authority status."""

from __future__ import annotations

from ai_brain.stage2.conversation.models import (
    ConversationReplayResult,
    ConversationReplayStatus,
)
from ai_brain.stage2.education.artifact_authority import (
    EducationalArtifactAuthorityVerifier,
)


def replay_conversation(service, conversation_id: str) -> ConversationReplayResult:
    try:
        service.conversations.verify(structural_only=True)
        conversation = service.conversations.get(conversation_id)
        turns = service.conversations.turns(conversation_id)
    except (KeyError, TypeError, ValueError):
        return ConversationReplayResult(
            conversation_id,
            ConversationReplayStatus.INVALID_CONVERSATION,
            None,
            0,
            "INVALID_HISTORY",
        )
    authority = "CURRENT"
    status = ConversationReplayStatus.CURRENT
    if conversation.active_tutor_session_id:
        try:
            historical = EducationalArtifactAuthorityVerifier(
                service.education
            ).verify()
        except (KeyError, TypeError, ValueError):
            return ConversationReplayResult(
                conversation_id,
                ConversationReplayStatus.STALE_EDUCATIONAL_SESSION,
                conversation.state.value,
                len(turns),
                "INVALID_HISTORY",
            )
        authority = historical["current_authority_status"]
        if authority != "CURRENT":
            status = ConversationReplayStatus.HISTORY_VALID_BUT_STALE
    try:
        service.progress.verify(
            authority_check=(
                service._verify_progress_authority if authority == "CURRENT" else None
            ),
            structural_only=authority != "CURRENT",
        )
    except (KeyError, TypeError, ValueError):
        return ConversationReplayResult(
            conversation_id,
            ConversationReplayStatus.INVALID_PROGRESS_EVENT,
            conversation.state.value,
            len(turns),
            authority,
        )
    if conversation.pending_action_id:
        try:
            action = service.conversations.get_pending(conversation.pending_action_id)
            if action.dependency_snapshot != service._dependency_snapshot():
                status = ConversationReplayStatus.STALE_PENDING_ACTION
                authority = "STALE_PENDING_ACTION"
        except (KeyError, TypeError, ValueError):
            status = ConversationReplayStatus.STALE_PENDING_ACTION
            authority = "STALE_PENDING_ACTION"
    return ConversationReplayResult(
        conversation_id, status, conversation.state.value, len(turns), authority
    )
