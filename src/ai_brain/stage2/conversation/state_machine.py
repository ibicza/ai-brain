"""Explicit bounded conversation transition table."""

from ai_brain.stage2.conversation.models import ConversationIntent, ConversationState

ALLOWED = {
    ConversationState.IDLE: {
        ConversationState.IDLE,
        ConversationState.EXERCISE_ACTIVE,
        ConversationState.AWAITING_CONFIRMATION,
        ConversationState.AWAITING_CLARIFICATION,
        ConversationState.PAUSED,
        ConversationState.CLOSED,
    },
    ConversationState.EXERCISE_ACTIVE: {
        ConversationState.EXERCISE_ACTIVE,
        ConversationState.AWAITING_CONFIRMATION,
        ConversationState.AWAITING_CLARIFICATION,
        ConversationState.PAUSED,
        ConversationState.CLOSED,
    },
    ConversationState.AWAITING_CONFIRMATION: {
        ConversationState.IDLE,
        ConversationState.EXERCISE_ACTIVE,
        ConversationState.PAUSED,
        ConversationState.CLOSED,
    },
    ConversationState.AWAITING_CLARIFICATION: {
        ConversationState.IDLE,
        ConversationState.EXERCISE_ACTIVE,
        ConversationState.PAUSED,
        ConversationState.CLOSED,
    },
    ConversationState.PAUSED: {
        ConversationState.IDLE,
        ConversationState.EXERCISE_ACTIVE,
        ConversationState.AWAITING_CONFIRMATION,
        ConversationState.AWAITING_CLARIFICATION,
        ConversationState.CLOSED,
    },
    ConversationState.CLOSED: set(),
}


def require_action_allowed(
    state: ConversationState,
    intent: ConversationIntent,
    *,
    active_session: bool,
    pending_action: bool,
) -> None:
    if state is ConversationState.CLOSED:
        raise ValueError("conversation is closed")
    if state is ConversationState.AWAITING_CONFIRMATION and intent not in {
        ConversationIntent.CONFIRM_PENDING_ACTION,
        ConversationIntent.CANCEL_PENDING_ACTION,
        ConversationIntent.PAUSE,
        ConversationIntent.END_CONVERSATION,
    }:
        raise ValueError(
            "only confirm, cancel, pause, or end is allowed while confirmation is pending"
        )
    if state is ConversationState.PAUSED and intent not in {
        ConversationIntent.RESUME,
        ConversationIntent.END_CONVERSATION,
    }:
        raise ValueError("conversation is paused")
    if (
        intent
        in {
            ConversationIntent.SUBMIT_ANSWER,
            ConversationIntent.REQUEST_HINT,
            ConversationIntent.REQUEST_SOLUTION,
        }
        and not active_session
    ):
        raise ValueError("this action requires an active exercise")
    if (
        intent
        in {
            ConversationIntent.CONFIRM_PENDING_ACTION,
            ConversationIntent.CANCEL_PENDING_ACTION,
        }
        and not pending_action
    ):
        raise ValueError("this action requires one pending confirmation")


def require_transition(old: ConversationState, new: ConversationState) -> None:
    if new not in ALLOWED[old]:
        raise ValueError(f"invalid conversation transition: {old.value}->{new.value}")
