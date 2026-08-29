"""Bounded chemistry-free conversation facade for generic education."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.education.generic_service import GenericEducationalService
from ai_brain.stage2.facts.canonical import content_hash


@dataclass(frozen=True)
class GenericConversation:
    conversation_id: str
    learner_id: str
    language: str
    active_exercise_id: str | None
    turn_count: int


class GenericConversationalTutorService:
    """Routes a deliberately small controlled language through one provider."""

    def __init__(self, education: GenericEducationalService) -> None:
        self.education = education
        self._conversations: dict[str, GenericConversation] = {}

    def start(self, learner_id: str, *, language: str = "en") -> GenericConversation:
        if not learner_id.strip() or language not in {"ru", "en"}:
            raise ValueError("generic conversation identity or language is invalid")
        identity = f"generic.conversation.{content_hash((learner_id, language))[:24]}"
        conversation = GenericConversation(identity, learner_id, language, None, 0)
        self._conversations[identity] = conversation
        return conversation

    def turn(self, conversation_id: str, text: str):
        conversation = self._conversations[conversation_id]
        result = self.education.provider.converse(
            text, exercise_id=conversation.active_exercise_id
        )
        exercise_id = getattr(result, "exercise_id", None)
        updated = GenericConversation(
            conversation.conversation_id,
            conversation.learner_id,
            conversation.language,
            exercise_id or conversation.active_exercise_id,
            conversation.turn_count + 1,
        )
        self._conversations[conversation_id] = updated
        return result

    def show(self, conversation_id: str) -> GenericConversation:
        return self._conversations[conversation_id]
