"""Bounded chemistry-free conversation facade for generic education."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.conversation.operations import (
    TutorOperationJournal,
    TutorOperationStatus,
    TutorSagaCoordinator,
)
from ai_brain.stage2.conversation.persistence import ConversationStore
from ai_brain.stage2.education.generic_service import GenericEducationalService
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.generic_ledger import GenericPersistentLedger
from ai_brain.stage2.progress.persistence import LearnerProgressStore


@dataclass(frozen=True)
class GenericConversation:
    conversation_id: str
    learner_id: str
    language: str
    active_exercise_id: str | None
    turn_count: int
    conversation_hash: str = ""


class GenericConversationalTutorService:
    """Routes a deliberately small controlled language through one provider."""

    def __init__(
        self,
        education: GenericEducationalService,
        *,
        state_root: Path | None = None,
        crash_injector=None,
    ) -> None:
        self.education = education
        pack_hash = education.domain_runtime.pack_hash()
        root = (
            state_root
            or Path(tempfile.gettempdir())
            / "ai-brain-generic-runtime"
            / str(os.getpid())
            / pack_hash
        ).resolve()
        conversations = ConversationStore.open_or_initialize(root / "conversation")
        progress = LearnerProgressStore.open_or_initialize(root / "progress")
        self._conversations = GenericPersistentLedger(
            conversations, "generic_conversation_records"
        )
        self._progress = GenericPersistentLedger(progress, "generic_progress_records")
        self.operations = TutorOperationJournal.open_or_initialize(root / "operations")
        self.operations.crash_injector = crash_injector
        self.saga = TutorSagaCoordinator(self.operations)

    def start(self, learner_id: str, *, language: str = "en") -> GenericConversation:
        if not learner_id.strip() or language not in {"ru", "en"}:
            raise ValueError("generic conversation identity or language is invalid")
        identity = f"generic.conversation.{content_hash((learner_id, language))[:24]}"
        provisional = GenericConversation(identity, learner_id, language, None, 0)
        body = {
            "conversation_id": provisional.conversation_id,
            "learner_id": provisional.learner_id,
            "language": provisional.language,
            "active_exercise_id": provisional.active_exercise_id,
            "turn_count": provisional.turn_count,
        }
        conversation = GenericConversation(**body, conversation_hash=content_hash(body))
        self._conversations.put(
            f"{identity}.turn.0", f"start.{identity}", "CONVERSATION", conversation
        )
        return conversation

    def turn(self, conversation_id: str, text: str):
        conversation = self.show(conversation_id)
        pending = tuple(
            item
            for item in self.operations.pending_recovery()
            if item.conversation_id == conversation_id
            and item.intent == "GENERIC_CONTROLLED_TURN"
        )
        if len(pending) > 1:
            raise ValueError("multiple generic tutor operations require recovery")
        if pending:
            return self._recover(pending[0], conversation, text)
        operation = self.operations.prepare(
            learner_id=conversation.learner_id,
            conversation_id=conversation.conversation_id,
            intent="GENERIC_CONTROLLED_TURN",
            input_hash=content_hash(
                {"text": text, "conversation_hash": conversation.conversation_hash}
            ),
            expected_educational_side_effects=("COMMAND_RESPONSE",),
            expected_progress_side_effects=("TURN_OBSERVED",),
            expected_conversation_result="PUBLIC_GENERIC_TURN",
        )
        if operation.status is TutorOperationStatus.COMPLETED:
            return self.education.provider.result_for_operation(operation.operation_id)
        try:
            if operation.status is TutorOperationStatus.RECOVERY_REQUIRED:
                return self._recover(operation, conversation, text)
            if operation.status is not TutorOperationStatus.PREPARED:
                raise ValueError("generic tutor operation has an invalid stage")
            return self._execute_prepared(operation, conversation, text)
        except Exception as error:
            current = self.operations.get(operation.operation_id)
            if current.status not in {
                TutorOperationStatus.COMPLETED,
                TutorOperationStatus.FAILED,
                TutorOperationStatus.RECOVERY_REQUIRED,
            }:
                self.operations.recovery_required(
                    current,
                    content_hash(
                        {"error_type": type(error).__name__, "message": str(error)}
                    ),
                )
            raise

    def _execute_prepared(self, operation, conversation, text):
        operation, _ = self.saga.apply_store_stage(
            operation,
            TutorOperationStatus.EDUCATION_APPLIED,
            store_id="EducationalSessionStore",
            write=lambda operation_id: self._write_education(
                operation_id, conversation, text
            ),
            inspect=self.education.provider.inspect_operation,
        )
        result, result_hash, body, updated = self._turn_values(
            operation.operation_id, conversation
        )
        operation, _ = self.saga.apply_store_stage(
            operation,
            TutorOperationStatus.PROGRESS_APPLIED,
            store_id="LearnerProgressStore",
            write=lambda operation_id: self._write_progress(
                operation_id, conversation, result_hash
            ),
            inspect=self._progress.inspect_operation,
        )
        operation, _ = self.saga.apply_store_stage(
            operation,
            TutorOperationStatus.CONVERSATION_COMMITTED,
            store_id="ConversationStore",
            write=lambda operation_id: self._write_conversation(
                operation_id, conversation, updated, body, result_hash
            ),
            inspect=self._conversations.inspect_operation,
        )
        _, published = self.saga.publish(operation, result_hash, lambda: result)
        return published

    def _recover(self, operation, conversation, text):
        def write_progress(operation_id):
            result = self.education.provider.result_for_operation(operation_id)
            self._write_progress(operation_id, conversation, _result_hash(result))

        def write_conversation(operation_id):
            _, result_hash, body, updated = self._turn_values(
                operation_id, conversation
            )
            self._write_conversation(
                operation_id, conversation, updated, body, result_hash
            )

        recovered = self.saga.recover(
            operation.operation_id,
            (
                (
                    TutorOperationStatus.EDUCATION_APPLIED,
                    "EducationalSessionStore",
                    lambda operation_id: self._write_education(
                        operation_id, conversation, text
                    ),
                    self.education.provider.inspect_operation,
                ),
                (
                    TutorOperationStatus.PROGRESS_APPLIED,
                    "LearnerProgressStore",
                    write_progress,
                    self._progress.inspect_operation,
                ),
                (
                    TutorOperationStatus.CONVERSATION_COMMITTED,
                    "ConversationStore",
                    write_conversation,
                    self._conversations.inspect_operation,
                ),
            ),
        )
        result = self.education.provider.result_for_operation(operation.operation_id)
        result_hash = _result_hash(result)
        _, published = self.saga.publish(recovered, result_hash, lambda: result)
        return published

    def _write_education(self, operation_id, conversation, text):
        return self.education.provider.converse(
            text,
            exercise_id=conversation.active_exercise_id,
            operation_id=operation_id,
        )

    def _write_progress(self, operation_id, conversation, result_hash):
        return self._progress.put(
            f"progress.{operation_id}",
            operation_id,
            "TURN_OBSERVED",
            {
                "learner_id": conversation.learner_id,
                "conversation_id": conversation.conversation_id,
                "response_hash": result_hash,
                "pack_hash": self.education.domain_runtime.pack_hash(),
            },
        )

    def _turn_values(self, operation_id, conversation):
        result = self.education.provider.result_for_operation(operation_id)
        result_hash = _result_hash(result)
        exercise_id = getattr(result, "exercise_id", None)
        body = {
            "conversation_id": conversation.conversation_id,
            "learner_id": conversation.learner_id,
            "language": conversation.language,
            "active_exercise_id": exercise_id or conversation.active_exercise_id,
            "turn_count": conversation.turn_count + 1,
        }
        updated = GenericConversation(**body, conversation_hash=content_hash(body))
        return result, result_hash, body, updated

    def _write_conversation(
        self, operation_id, conversation, updated, body, result_hash
    ):
        return self._conversations.put(
            f"{conversation.conversation_id}.turn.{updated.turn_count}",
            operation_id,
            "CONVERSATION",
            {
                **body,
                "conversation_hash": updated.conversation_hash,
                "public_response_hash": result_hash,
            },
        )

    def show(self, conversation_id: str) -> GenericConversation:
        candidates = tuple(
            item
            for item in self._conversations.records(kind="CONVERSATION")
            if item[0].startswith(f"{conversation_id}.turn.")
        )
        if not candidates:
            raise KeyError(conversation_id)
        payload = max(candidates, key=lambda item: item[2]["turn_count"])[2]
        payload.pop("public_response_hash", None)
        return GenericConversation(**payload)

    def query(self, conversation_id: str, request: dict):
        return self.turn(conversation_id, f"query:{canonical_json(request)}")

    def verify_persistence(self) -> dict[str, object]:
        return {
            "education": self.education.provider.verify_persistence(),
            "conversation": self._conversations.verify(),
            "progress": self._progress.verify(),
            "operations": self.operations.verify(),
        }


def _result_hash(result) -> str:
    if hasattr(result, "__dataclass_fields__"):
        from dataclasses import asdict

        return content_hash(asdict(result))
    return content_hash(result)
