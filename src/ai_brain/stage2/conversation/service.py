"""Bounded orchestration over trusted education and observable progress."""

from __future__ import annotations

import re
import secrets
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.conversation.intents import parse_intent
from ai_brain.stage2.conversation.models import (
    ConversationIntent,
    ConversationState,
    ConversationTurn,
    PendingAction,
    PendingActionStatus,
    PublicConversationResponse,
    PublicPendingAction,
    Speaker,
    TutorConversation,
)
from ai_brain.stage2.conversation.operations import (
    TutorOperationJournal,
    TutorOperationStatus,
    TutorSagaCoordinator,
)
from ai_brain.stage2.conversation.pending_actions import (
    authorize_pending,
    prepare_pending_action,
    public_pending,
    transition_pending,
)
from ai_brain.stage2.conversation.persistence import ConversationStore
from ai_brain.stage2.conversation.responses import response_hash, verify_public_response
from ai_brain.stage2.conversation.state_machine import (
    require_action_allowed,
    require_transition,
)
from ai_brain.stage2.conversation.version import CONVERSATIONAL_SCHEMA_VERSION
from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.currentness import (
    evaluate_entry_currentness,
    require_current,
)
from ai_brain.stage2.education.models import (
    AnswerParseStatus,
    ExerciseFamily,
    ExplanationMode,
    GradingStatus,
    PublicExercise,
    PublicHint,
    PublicSolution,
    PublicSubmissionResult,
    PublicTutorSessionHandle,
)
from ai_brain.stage2.facts.canonical import canonical_json, content_hash, utc_now
from ai_brain.stage2.generic_ledger import GenericPersistentLedger
from ai_brain.stage2.progress.events import make_progress_event
from ai_brain.stage2.progress.models import ProgressEventKind
from ai_brain.stage2.progress.persistence import LearnerProgressStore
from ai_brain.stage2.progress.projection import project_progress
from ai_brain.stage2.progress.recommendations import recommend_exercise
from ai_brain.stage2.progress.rendering import render_progress_summary
from ai_brain.stage2.router.models import (
    DependencySnapshot,
    NextAction,
    RequestEnvelope,
    RequestSourceKind,
    ResponseStage,
    RouteAuthority,
    RouteDecision,
    RouteStatus,
    RouteTarget,
    ToolCallProposal,
    UnifiedResponseEnvelope,
)


class ConversationalTutorService:
    def __init__(
        self,
        education,
        conversations: ConversationStore,
        progress: LearnerProgressStore,
        operations: TutorOperationJournal | None = None,
    ) -> None:
        self.education = education
        self.conversations = conversations
        self.progress = progress
        self.operations = operations or TutorOperationJournal.open_or_initialize(
            conversations.root / "operations"
        )
        self.saga = TutorSagaCoordinator(self.operations)
        self._education_stage_ledger = GenericPersistentLedger(
            education.store, "legacy_saga_stage_records"
        )
        self._legacy_outcomes = GenericPersistentLedger(
            education.store, "legacy_saga_outcome_records"
        )
        self._progress_stage_ledger = GenericPersistentLedger(
            progress, "legacy_saga_stage_records"
        )
        self._conversation_stage_ledger = GenericPersistentLedger(
            conversations, "legacy_saga_stage_records"
        )
        self.progress.authority_check = self._verify_progress_authority
        self.conversations.semantic_authority = self
        self._pending_authority: dict[str, tuple[object, object]] = {}
        self._catalog_candidates = self._index_catalog_candidates()

    @classmethod
    def open(
        cls, education, conversation_root: Path, progress_root: Path
    ) -> ConversationalTutorService:
        return cls(
            education,
            ConversationStore.open_or_initialize(conversation_root),
            LearnerProgressStore.open_or_initialize(progress_root),
            TutorOperationJournal.open_or_initialize(conversation_root / "operations"),
        )

    def start(
        self,
        learner_id: str,
        *,
        language: str = "ru",
        conversation_id: str | None = None,
        created_at: str | None = None,
    ) -> PublicConversationResponse:
        if not learner_id or language not in {"ru", "en"}:
            raise ValueError("explicit learner and ru/en language are required")
        timestamp = created_at or utc_now()
        body = {
            "conversation_id": conversation_id
            or "conversation_" + secrets.token_urlsafe(18),
            "learner_id": learner_id,
            "language": language,
            "state": ConversationState.IDLE,
            "previous_active_state": ConversationState.IDLE,
            "active_tutor_session_id": None,
            "pending_action_id": None,
            "pending_clarification_id": None,
            "turn_hashes": (),
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_event_hash": None,
            "schema_version": CONVERSATIONAL_SCHEMA_VERSION,
        }
        conversation = TutorConversation(**body, conversation_hash=content_hash(body))
        self.conversations.create(conversation)
        return self._response(
            conversation,
            "STARTED",
            "Занятие начато." if language == "ru" else "Tutoring started.",
        )

    def turn(
        self, conversation_id: str, text: str, *, created_at: str | None = None
    ) -> PublicConversationResponse:
        conversation = self.conversations.get(conversation_id)
        pending_recovery = tuple(
            item
            for item in self.operations.pending_recovery()
            if item.conversation_id == conversation_id
        )
        if len(pending_recovery) > 1:
            raise ValueError("multiple legacy tutor operations require recovery")
        if pending_recovery:
            return self._recover_turn(pending_recovery[0], text, created_at)
        parsed = parse_intent(text, conversation.language)
        if (
            parsed.intent is ConversationIntent.CLARIFY
            and conversation.active_tutor_session_id is not None
            and conversation.state
            in {
                ConversationState.EXERCISE_ACTIVE,
                ConversationState.AWAITING_CLARIFICATION,
            }
        ):
            parsed = self._parse_context_answer(conversation, text, parsed)
        if parsed.intent is ConversationIntent.CONFIRM_PENDING_ACTION:
            return self.confirm(
                conversation_id,
                conversation.pending_action_id or "",
                created_at=created_at,
                original_text=text,
            )
        if parsed.intent is ConversationIntent.CANCEL_PENDING_ACTION:
            return self.cancel(
                conversation_id,
                conversation.pending_action_id or "",
                created_at=created_at,
                original_text=text,
            )
        working = conversation
        if (
            conversation.state is ConversationState.AWAITING_CLARIFICATION
            and parsed.intent
            not in {ConversationIntent.CLARIFY, ConversationIntent.COMPOSITE_REQUIRED}
        ):
            working = self._change(
                conversation,
                state=conversation.previous_active_state,
                pending_clarification_id=None,
            )
        require_action_allowed(
            working.state,
            parsed.intent,
            active_session=working.active_tutor_session_id is not None,
            pending_action=working.pending_action_id is not None,
        )
        operation = self.operations.prepare(
            learner_id=conversation.learner_id,
            conversation_id=conversation.conversation_id,
            intent=parsed.intent.value,
            input_hash=content_hash(
                {"text": text, "conversation_hash": conversation.conversation_hash}
            ),
            expected_educational_side_effects=(parsed.intent.value,),
            expected_progress_side_effects=(parsed.intent.value,),
            expected_conversation_result="PUBLIC_TURN",
            created_at=created_at,
        )
        if operation.status is not TutorOperationStatus.PREPARED:
            raise ValueError("tutor operation retry requires explicit recovery")
        try:
            outcome = self._execute(
                working,
                parsed,
                text,
                created_at=created_at,
                operation_id=operation.operation_id,
            )
            new, response = outcome[:2]
            pending_action = outcome[2] if len(outcome) == 3 else None
            self._legacy_outcomes.put(
                f"outcome.{operation.operation_id}",
                operation.operation_id,
                "LEGACY_TURN_OUTCOME",
                {
                    "old": conversation,
                    "new": new,
                    "parsed_intent": parsed.intent.value,
                    "original_text": text,
                    "response": response,
                    "pending_action": pending_action,
                },
            )
            education_hashes = self._education_operation_hashes(operation.operation_id)
            operation, _ = self.saga.apply_store_stage(
                operation,
                TutorOperationStatus.EDUCATION_APPLIED,
                store_id="EducationalSessionStore",
                write=lambda operation_id: self._education_stage_ledger.put(
                    f"education.{operation_id}",
                    operation_id,
                    "LEGACY_EDUCATION_STAGE",
                    {"committed_event_hashes": education_hashes},
                ),
                inspect=self._education_stage_ledger.inspect_operation,
                committed_at=created_at,
            )
            progress_hashes = tuple(
                item.event_hash
                for item in self.progress.events(conversation.learner_id)
                if item.operation_id == operation.operation_id
            )
            operation, _ = self.saga.apply_store_stage(
                operation,
                TutorOperationStatus.PROGRESS_APPLIED,
                store_id="LearnerProgressStore",
                write=lambda operation_id: self._progress_stage_ledger.put(
                    f"progress.{operation_id}",
                    operation_id,
                    "LEGACY_PROGRESS_STAGE",
                    {"committed_event_hashes": progress_hashes},
                ),
                inspect=self._progress_stage_ledger.inspect_operation,
                committed_at=created_at,
            )
            published = {}

            def write_conversation(operation_id):
                result = self._record(
                    conversation,
                    new,
                    parsed.intent,
                    text,
                    response,
                    created_at=created_at,
                    pending_action=pending_action,
                    operation_id=operation_id,
                )
                published["result"] = result
                self._conversation_stage_ledger.put(
                    f"conversation.{operation_id}",
                    operation_id,
                    "LEGACY_CONVERSATION_STAGE",
                    {"public_response_hash": response_hash(result)},
                )

            operation, _ = self.saga.apply_store_stage(
                operation,
                TutorOperationStatus.CONVERSATION_COMMITTED,
                store_id="ConversationStore",
                write=write_conversation,
                inspect=self._conversation_stage_ledger.inspect_operation,
                committed_at=created_at,
            )
            result = published.get("result")
            if result is None:
                raise ValueError("legacy conversation stage did not publish a response")
            _, result = self.saga.publish(
                operation, response_hash(result), lambda: result
            )
            return result
        except Exception as error:
            current = self.operations.get(operation.operation_id)
            failure = content_hash(
                {"type": type(error).__name__, "message": str(error)}
            )
            if current.status is TutorOperationStatus.PREPARED:
                if self._legacy_outcomes.inspect_operation(operation.operation_id):
                    self.operations.recovery_required(current, failure)
                else:
                    self.operations.failed(current, failure)
            elif current.status not in {
                TutorOperationStatus.COMPLETED,
                TutorOperationStatus.FAILED,
                TutorOperationStatus.RECOVERY_REQUIRED,
            }:
                self.operations.recovery_required(current, failure)
            raise

    def _education_operation_hashes(self, operation_id: str) -> tuple[str, ...]:
        return tuple(
            event.event_hash
            for session_id in self.education.store.session_ids()
            for event in self.education.store.events(session_id)
            if event.operation_id == operation_id
        )

    def _recover_turn(self, operation, retry_text, created_at):
        _, kind, payload, _ = self._legacy_outcomes.get(
            f"outcome.{operation.operation_id}"
        )
        if kind != "LEGACY_TURN_OUTCOME" or payload["original_text"] != retry_text:
            raise ValueError("legacy recovery input does not match prepared authority")
        old = _conversation_from_row(payload["old"])
        new = _conversation_from_row(payload["new"])
        response = _public_response_from_row(payload["response"])
        pending_action = (
            _pending_action_from_row(payload["pending_action"])
            if payload["pending_action"] is not None
            else None
        )
        intent = ConversationIntent(payload["parsed_intent"])

        def education_write(operation_id):
            self._education_stage_ledger.put(
                f"education.{operation_id}",
                operation_id,
                "LEGACY_EDUCATION_STAGE",
                {
                    "committed_event_hashes": self._education_operation_hashes(
                        operation_id
                    )
                },
            )

        def progress_write(operation_id):
            hashes = tuple(
                item.event_hash
                for item in self.progress.events(old.learner_id)
                if item.operation_id == operation_id
            )
            self._progress_stage_ledger.put(
                f"progress.{operation_id}",
                operation_id,
                "LEGACY_PROGRESS_STAGE",
                {"committed_event_hashes": hashes},
            )

        def conversation_write(operation_id):
            existing = tuple(
                item
                for item in self.conversations.turns(old.conversation_id)
                if item.operation_id == operation_id
            )
            if not existing:
                self._record(
                    old,
                    new,
                    intent,
                    retry_text,
                    response,
                    created_at=created_at,
                    pending_action=pending_action,
                    operation_id=operation_id,
                )
            self._conversation_stage_ledger.put(
                f"conversation.{operation_id}",
                operation_id,
                "LEGACY_CONVERSATION_STAGE",
                {"public_response_hash": response_hash(response)},
            )

        recovered = self.saga.recover(
            operation.operation_id,
            (
                (
                    TutorOperationStatus.EDUCATION_APPLIED,
                    "EducationalSessionStore",
                    education_write,
                    self._education_stage_ledger.inspect_operation,
                ),
                (
                    TutorOperationStatus.PROGRESS_APPLIED,
                    "LearnerProgressStore",
                    progress_write,
                    self._progress_stage_ledger.inspect_operation,
                ),
                (
                    TutorOperationStatus.CONVERSATION_COMMITTED,
                    "ConversationStore",
                    conversation_write,
                    self._conversation_stage_ledger.inspect_operation,
                ),
            ),
        )
        _, result = self.saga.publish(
            recovered, response_hash(response), lambda: response
        )
        return result

    def confirm(
        self,
        conversation_id: str,
        pending_id: str,
        *,
        created_at: str | None = None,
        original_text: str = "CONFIRM",
    ) -> PublicConversationResponse:
        conversation = self.conversations.get(conversation_id)
        require_action_allowed(
            conversation.state,
            ConversationIntent.CONFIRM_PENDING_ACTION,
            active_session=conversation.active_tutor_session_id is not None,
            pending_action=conversation.pending_action_id is not None,
        )
        if pending_id != conversation.pending_action_id:
            raise ValueError("pending action handle mismatch")
        action = self.conversations.get_pending(pending_id)
        if action.status is PendingActionStatus.EXECUTING:
            failed = transition_pending(action, PendingActionStatus.FAILED)
            self.conversations.replace_pending(action, failed)
            return self._failed_pending_response(
                conversation,
                action,
                original_text,
                "Ambiguous executing action was closed as verified FAILED.",
                created_at,
            )
        try:
            executing = authorize_pending(
                action,
                learner_id=conversation.learner_id,
                conversation_id=conversation_id,
                language=conversation.language,
                dependency_snapshot=self._dependency_snapshot(),
                now=created_at,
            )
        except ValueError as error:
            message = str(error)
            if "expired" in message:
                terminal = transition_pending(action, PendingActionStatus.EXPIRED)
            elif "dependencies changed" in message:
                terminal = transition_pending(action, PendingActionStatus.STALE)
            else:
                raise
            self.conversations.replace_pending(action, terminal)
            return self._failed_pending_response(
                conversation, action, original_text, message, created_at
            )
        if action.action_kind != "EXPLAIN_MOLAR_MASS":
            raise ValueError("unsupported pending action kind")
        # Persist EXECUTING before invocation. Recovery never replays an ambiguous
        # physical invocation, so this is at-most-once execution, not a claim of
        # physically exactly-once CPU work across process death.
        self.conversations.replace_pending(action, executing)
        authority = self._pending_authority.pop(action.pending_id, None)
        if authority is None:
            authority = _restore_pending_authority(action.payload, self.education)
            if authority is None:
                stale = transition_pending(executing, PendingActionStatus.STALE)
                self.conversations.replace_pending(executing, stale)
                return self._failed_pending_response(
                    conversation,
                    action,
                    original_text,
                    "Pending action authority cannot be reconstructed exactly.",
                    created_at,
                )
        prepared, proposal = authority
        if (
            prepared.response_hash,
            proposal.proposal_hash,
        ) != action.prepared_authority_hashes:
            stale = transition_pending(executing, PendingActionStatus.STALE)
            self.conversations.replace_pending(executing, stale)
            return self._failed_pending_response(
                conversation,
                action,
                original_text,
                "Pending action authority hash mismatch.",
                created_at,
            )
        try:
            result = self.education.confirm_explanation(
                prepared,
                proposal,
                identity=conversation.learner_id,
                language=conversation.language,
                mode=ExplanationMode.FULL,
            )
        except Exception as error:  # noqa: BLE001 - persist exact pending failure
            failed = transition_pending(executing, PendingActionStatus.FAILED)
            self.conversations.replace_pending(executing, failed)
            return self._failed_pending_response(
                conversation,
                action,
                original_text,
                f"Trusted calculation failed: {type(error).__name__}.",
                created_at,
            )
        executed = transition_pending(executing, PendingActionStatus.EXECUTED)
        self.conversations.replace_pending(executing, executed)
        new = self._change(
            conversation,
            state=action.previous_state,
            pending_action_id=None,
            updated_at=created_at or utc_now(),
        )
        response = self._response(new, "EXPLANATION", result.text or "")
        return self._record(
            conversation,
            new,
            ConversationIntent.CONFIRM_PENDING_ACTION,
            original_text,
            response,
            created_at=created_at,
        )

    def _failed_pending_response(
        self, conversation, action, original_text, message, created_at
    ):
        new = self._change(
            conversation,
            state=action.previous_state,
            pending_action_id=None,
            updated_at=created_at or utc_now(),
        )
        response = self._response(new, "PENDING_ACTION_FAILED", message)
        return self._record(
            conversation,
            new,
            ConversationIntent.CONFIRM_PENDING_ACTION,
            original_text,
            response,
            created_at=created_at,
        )

    def cancel(
        self,
        conversation_id: str,
        pending_id: str,
        *,
        created_at: str | None = None,
        original_text: str = "CANCEL",
    ) -> PublicConversationResponse:
        conversation = self.conversations.get(conversation_id)
        if pending_id != conversation.pending_action_id:
            raise ValueError("pending action handle mismatch")
        action = self.conversations.get_pending(pending_id)
        if (
            action.status is not PendingActionStatus.PREPARED
            or action.learner_id != conversation.learner_id
            or action.conversation_id != conversation_id
        ):
            raise ValueError("pending action is not cancellable")
        provisional = replace(
            action, status=PendingActionStatus.CANCELLED, pending_hash=""
        )
        body = asdict(provisional)
        body.pop("pending_hash")
        cancelled = replace(provisional, pending_hash=content_hash(body))
        self.conversations.replace_pending(action, cancelled)
        new = self._change(
            conversation,
            state=action.previous_state,
            pending_action_id=None,
            updated_at=created_at or utc_now(),
        )
        response = self._response(
            new,
            "CANCELLED",
            "Расчёт отменён." if new.language == "ru" else "Calculation cancelled.",
        )
        return self._record(
            conversation,
            new,
            ConversationIntent.CANCEL_PENDING_ACTION,
            original_text,
            response,
            created_at=created_at,
        )

    def progress_summary(self, conversation_id: str):
        conversation = self.conversations.get(conversation_id)
        events = self.progress.events(conversation.learner_id)
        projections = self._project(conversation.learner_id, events)
        current_authority = self._progress_is_current(events)
        recommendation = (
            self._recommend(conversation, projections, required=False)
            if current_authority
            else None
        )
        return render_progress_summary(
            projections,
            recommendation,
            events=events,
            current_authority=current_authority,
        )

    def export_progress(self, learner_id: str) -> str:
        return self.progress.export(learner_id)

    def reset_progress(
        self, learner_id: str, *, confirmed: bool, created_at: str | None = None
    ):
        if not confirmed:
            raise ValueError("progress reset requires explicit confirmation")
        events = self.progress.events(learner_id)
        if not events:
            raise ValueError("no observable progress exists for this learner")
        if not self._progress_is_current(events):
            raise ValueError(
                "stale progress history cannot authorize a new reset event"
            )
        last = events[-1]
        event = make_progress_event(
            learner_id=learner_id,
            conversation_id=last.conversation_id,
            tutor_session_id=last.tutor_session_id,
            catalog_entry_hash=last.catalog_entry_hash,
            semantic_key_hash=last.semantic_key_hash,
            concept_ids=self._concept_ids(),
            event_kind=ProgressEventKind.PROGRESS_RESET,
            sequence=len(events) + 1,
            previous_event_hash=last.event_hash,
            observed_at=created_at,
        )
        self.progress.append(event)
        return {"status": "RESET", "learner_id": learner_id}

    def delete_progress(self, learner_id: str, *, confirmed: bool):
        if not confirmed:
            raise ValueError("progress deletion requires explicit confirmation")
        return {
            "status": "DELETED",
            "learner_id": learner_id,
            "deleted_event_count": self.progress.delete_learner(learner_id),
        }

    def _execute(
        self, conversation, parsed, raw_text, *, created_at=None, operation_id=None
    ):
        intent = parsed.intent
        language = conversation.language
        timestamp = created_at or utc_now()
        if intent in {ConversationIntent.START_TUTORING}:
            return conversation, self._response(
                conversation,
                "STARTED",
                "Занятие уже доступно." if language == "ru" else "Tutoring is ready.",
            )
        if intent in {
            ConversationIntent.REQUEST_EXERCISE,
            ConversationIntent.REQUEST_NEXT_EXERCISE,
        }:
            self._abandon_if_needed(
                conversation, created_at=timestamp, operation_id=operation_id
            )
            seed = len(conversation.turn_hashes)
            recommendation = None
            selected_entry = None
            if intent is ConversationIntent.REQUEST_NEXT_EXERCISE:
                events = self.progress.events(conversation.learner_id)
                projections = self._project(conversation.learner_id, events)
                recommendation = (
                    self._recommend(conversation, projections, required=False)
                    if self._progress_is_current(events)
                    else None
                )
                if recommendation is None:
                    return conversation, self._response(
                        conversation,
                        "NO_CURRENT_RECOMMENDATION",
                        "Нет актуальной задачи с выполненными предпосылками."
                        if language == "ru"
                        else "No current prerequisite-satisfied exercise is available.",
                    )
                selected_entry = self.education.catalog.by_entry_hash(
                    recommendation.selected_entry_hash
                )
            family = (
                selected_entry.exercise_spec.family
                if selected_entry
                else ExerciseFamily(parsed.payload.get("family", "MOLAR_MASS_SIMPLE"))
            )
            if selected_entry is not None:
                matches = [
                    x
                    for x in self.education.catalog.entries
                    if x.exercise_spec.family is family
                ]
                seed = matches.index(selected_entry)
            exercise = self.education.create_exercise(
                family,
                seed=seed,
                language=language,
                created_at=timestamp,
                operation_id=operation_id,
            )
            new = self._change(
                conversation,
                state=ConversationState.EXERCISE_ACTIVE,
                active_tutor_session_id=exercise.session.session_id,
                updated_at=timestamp,
            )
            self._observe(
                new,
                ProgressEventKind.EXERCISE_PRESENTED,
                created_at=timestamp,
                operation_id=operation_id,
            )
            return new, self._response(
                new,
                "EXERCISE",
                ("Решите задачу." if language == "ru" else "Solve this exercise.")
                + (
                    f" Recommendation: {recommendation.reason_code.value}."
                    if recommendation
                    else ""
                ),
                exercise=exercise,
            )
        if intent is ConversationIntent.SUBMIT_ANSWER:
            submission = self.education.submit_answer(
                conversation.active_tutor_session_id,
                parsed.payload["text"],
                created_at=timestamp,
                operation_id=operation_id,
            )
            self._observe(
                conversation,
                ProgressEventKind.ANSWER_GRADED,
                correct=submission.status.startswith("CORRECT"),
                grading=True,
                created_at=timestamp,
                operation_id=operation_id,
            )
            if submission.status.startswith("CORRECT"):
                self._observe(
                    conversation,
                    ProgressEventKind.EXERCISE_SOLVED,
                    correct=True,
                    grading=True,
                    created_at=timestamp,
                    operation_id=operation_id,
                )
            return conversation, self._response(
                conversation, "SUBMISSION", submission.feedback, submission=submission
            )
        if intent is ConversationIntent.REQUEST_HINT:
            hint = self.education.hint(
                conversation.active_tutor_session_id,
                created_at=timestamp,
                operation_id=operation_id,
            )
            self._observe(
                conversation,
                ProgressEventKind.HINT_USED,
                hint_level=hint.level,
                created_at=timestamp,
                operation_id=operation_id,
            )
            return conversation, self._response(
                conversation, "HINT", hint.text, hint=hint
            )
        if intent is ConversationIntent.REQUEST_SOLUTION:
            solution = self.education.show_solution(
                conversation.active_tutor_session_id,
                created_at=timestamp,
                operation_id=operation_id,
            )
            self._observe(
                conversation,
                ProgressEventKind.SOLUTION_REVEALED,
                solution=True,
                created_at=timestamp,
                operation_id=operation_id,
            )
            return conversation, self._response(
                conversation, "SOLUTION", solution.text, solution=solution
            )
        if intent is ConversationIntent.REQUEST_PROGRESS:
            summary = self.progress_summary(conversation.conversation_id)
            return conversation, self._response(
                conversation,
                "PROGRESS",
                "Наблюдаемый прогресс." if language == "ru" else "Observable progress.",
                progress=summary,
            )
        if intent is ConversationIntent.REQUEST_FACT:
            entry = next(
                (
                    item
                    for item in self.education.catalog.entries
                    if item.exercise_spec.family is ExerciseFamily.FACT_RETRIEVAL
                    and item.compilation_receipt.canonical_arguments.get(
                        "answer_predicate"
                    )
                    == parsed.payload["predicate"]
                    and item.compilation_receipt.canonical_arguments.get("symbol")
                    == parsed.payload["symbol"]
                ),
                None,
            )
            if entry is None:
                return conversation, self._response(
                    conversation,
                    "UNSUPPORTED_CAPABILITY",
                    "Этот факт отсутствует в доверенном каталоге."
                    if language == "ru"
                    else "That fact is not in the trusted catalog.",
                )
            require_current(evaluate_entry_currentness(self.education.chemistry, entry))
            root = next(
                node
                for node in entry.graph.nodes
                if node.node_id == entry.graph.root_result_node_id
            )
            label = "Ответ" if language == "ru" else "Answer"
            return conversation, self._response(
                conversation, "FACT", f"{label}: {root.exact_output}"
            )
        if intent is ConversationIntent.REQUEST_EXPLANATION:
            formula = self._formula(parsed.payload["text"])
            arguments = {
                "formula": formula,
                "mode": "conventional",
                "unit": "g/mol",
                "significant_digits": 8,
            }
            outcome = self.education._explain_tool_internal(
                "chemistry_molar_mass", arguments, language=language
            )
            if len(outcome) >= 3 and hasattr(outcome[2], "explanation_hash"):
                return conversation, self._response(
                    conversation,
                    "EXPLANATION",
                    outcome[2].text,
                )
            _, prepared, proposal = outcome
            action = prepare_pending_action(
                learner_id=conversation.learner_id,
                conversation_id=conversation.conversation_id,
                action_kind="EXPLAIN_MOLAR_MASS",
                request_hash=content_hash(raw_text),
                language=language,
                payload={
                    "tool_arguments": arguments,
                    "prepared_response": asdict(prepared),
                    "tool_proposal": asdict(proposal),
                    "request": asdict(
                        self.education.chemistry.unified._requests[proposal.request_id]
                    ),
                    "route_decision": asdict(
                        self.education.chemistry.unified._decisions[
                            proposal.route_decision_hash
                        ]
                    ),
                },
                dependency_snapshot=self._dependency_snapshot(),
                previous_state=conversation.state,
                prepared_authority_hashes=(
                    prepared.response_hash,
                    proposal.proposal_hash,
                ),
                created_at=timestamp,
            )
            self._pending_authority[action.pending_id] = (prepared, proposal)
            new = self._change(
                conversation,
                state=ConversationState.AWAITING_CONFIRMATION,
                pending_action_id=action.pending_id,
                updated_at=timestamp,
            )
            return (
                new,
                self._response(
                    new,
                    "CONFIRMATION_REQUIRED",
                    "Подтвердите расчёт."
                    if language == "ru"
                    else "Confirm the calculation.",
                    prepared_action=public_pending(action),
                ),
                action,
            )
        if intent is ConversationIntent.CHANGE_LANGUAGE:
            new_language = "en" if language == "ru" else "ru"
            new = self._change(
                conversation, language=new_language, updated_at=timestamp
            )
            return new, self._response(
                new,
                "LANGUAGE_CHANGED",
                "Language changed." if new_language == "en" else "Язык изменён.",
            )
        if intent is ConversationIntent.PAUSE:
            new = self._change(
                conversation,
                previous_active_state=conversation.state,
                state=ConversationState.PAUSED,
                updated_at=timestamp,
            )
            return new, self._response(
                new,
                "PAUSED",
                "Занятие на паузе." if language == "ru" else "Tutoring paused.",
            )
        if intent is ConversationIntent.RESUME:
            new = self._change(
                conversation,
                state=conversation.previous_active_state,
                updated_at=timestamp,
            )
            return new, self._response(
                new,
                "RESUMED",
                "Занятие продолжено." if language == "ru" else "Tutoring resumed.",
            )
        if intent is ConversationIntent.END_CONVERSATION:
            self._abandon_if_needed(
                conversation, created_at=timestamp, operation_id=operation_id
            )
            new = self._change(
                conversation, state=ConversationState.CLOSED, updated_at=timestamp
            )
            return new, self._response(
                new,
                "CLOSED",
                "Занятие завершено." if language == "ru" else "Tutoring ended.",
            )
        if intent is ConversationIntent.COMPOSITE_REQUIRED:
            return conversation, self._response(
                conversation,
                "COMPOSITE_REQUIRED",
                "Один запрос — одно действие."
                if language == "ru"
                else "Request one action at a time.",
            )
        clarification = (
            "Уточните один поддерживаемый учебный запрос."
            if language == "ru"
            else "Clarify one supported tutoring request."
        )
        new_state = (
            conversation.state
            if conversation.state is ConversationState.AWAITING_CONFIRMATION
            else ConversationState.AWAITING_CLARIFICATION
        )
        new = self._change(
            conversation,
            previous_active_state=conversation.state
            if new_state is ConversationState.AWAITING_CLARIFICATION
            else conversation.previous_active_state,
            state=new_state,
            pending_clarification_id="clarification_" + secrets.token_urlsafe(12)
            if new_state is ConversationState.AWAITING_CLARIFICATION
            else conversation.pending_clarification_id,
            updated_at=timestamp,
        )
        return new, self._response(
            new, "CLARIFY", clarification, clarification_prompt=clarification
        )

    def _parse_context_answer(self, conversation, text, fallback):
        _, spec, _, _ = self.education._load(conversation.active_tutor_session_id)
        answer = parse_student_answer(
            text,
            spec.accepted_answer_type,
            supported_symbols=set(
                self.education.chemistry.manifest["supported_elements"]
            ),
        )
        if answer.parse_status is AnswerParseStatus.PARSED:
            return replace(
                fallback,
                intent=ConversationIntent.SUBMIT_ANSWER,
                payload={"text": text},
                evidence=("strict-student-answer-parser",),
                intent_hash=content_hash(
                    {"original": fallback.intent_hash, "intent": "SUBMIT_ANSWER"}
                ),
            )
        return fallback

    def _observe(
        self,
        conversation,
        kind,
        *,
        correct=None,
        grading=False,
        hint_level=None,
        solution=False,
        created_at=None,
        operation_id=None,
    ):
        session = self.education.store.get_session(conversation.active_tutor_session_id)
        instance = self.education.store.get_artifact(
            session.exercise_hash, expected_kind="exercise_instance_internal"
        )
        spec = self.education.store.get_artifact(
            instance.exercise_spec_hash, expected_kind="exercise_spec"
        )
        events = self.progress.events(conversation.learner_id)
        previous = events[-1].event_hash if events else None
        concepts = self.education.domain_runtime.concepts_for_exercise_family(
            spec.family.value
        )
        prior_session_events = self.education.store.events(session.session_id)
        matching_types = {
            ProgressEventKind.EXERCISE_PRESENTED: "SESSION_PRESENTED",
            ProgressEventKind.ANSWER_GRADED: "ANSWER_GRADED",
            ProgressEventKind.HINT_USED: "HINT_ISSUED",
            ProgressEventKind.SOLUTION_REVEALED: "SOLUTION_REVEALED",
            ProgressEventKind.EXERCISE_SOLVED: "ANSWER_GRADED",
            ProgressEventKind.EXERCISE_ABANDONED: "SESSION_ABANDONED",
        }
        authority_event = next(
            (
                item
                for item in reversed(prior_session_events)
                if item.event_type == matching_types.get(kind)
            ),
            None,
        )
        if authority_event is None:
            raise ValueError("progress observation lacks educational authority event")
        grading_hash = None
        hint_hash = None
        explanation_hash = None
        authority_hashes = [authority_event.event_hash]
        if kind in {ProgressEventKind.ANSWER_GRADED, ProgressEventKind.EXERCISE_SOLVED}:
            grading_hash = authority_event.payload.get("grading_result_hash")
            grade = self.education.store.get_artifact(
                grading_hash, expected_kind="grading_result"
            )
            correct = grade.correctness_status in {
                GradingStatus.CORRECT,
                GradingStatus.CORRECT_EQUIVALENT_UNIT,
                GradingStatus.CORRECT_WITH_ACCEPTABLE_ROUNDING,
            }
            if kind is ProgressEventKind.EXERCISE_SOLVED and not correct:
                raise ValueError("solved progress requires a correct trusted grade")
            authority_hashes.append(grading_hash)
        hints = sum(item.event_type == "HINT_ISSUED" for item in prior_session_events)
        if kind is ProgressEventKind.HINT_USED:
            hint_hash = authority_event.payload["hint_hash"]
            hint = self.education.store.get_artifact(hint_hash, expected_kind="hint")
            hint_level = int(hint.level)
            authority_hashes.append(hint_hash)
        revealed = any(
            item.event_type == "SOLUTION_REVEALED" for item in prior_session_events
        )
        if kind is ProgressEventKind.SOLUTION_REVEALED:
            explanation_hash = authority_event.payload["explanation_hash"]
            authority_hashes.append(explanation_hash)
        event = make_progress_event(
            learner_id=conversation.learner_id,
            conversation_id=conversation.conversation_id,
            tutor_session_id=session.session_id,
            catalog_entry_hash=session.catalog_entry_hash,
            semantic_key_hash=instance.semantic_key_hash,
            concept_ids=concepts,
            event_kind=kind,
            sequence=len(events) + 1,
            previous_event_hash=previous,
            grading_result_hash=grading_hash,
            correct=correct,
            trusted_current=True,
            hint_level=hint_level,
            hint_count=hints,
            solution_revealed=revealed,
            hint_hash=hint_hash,
            explanation_hash=explanation_hash,
            observed_at=created_at,
            authority_hashes=tuple(authority_hashes),
            operation_id=operation_id,
        )
        self.progress.append(event, authority_check=self._verify_progress_authority)

    def _abandon_if_needed(self, conversation, *, created_at, operation_id=None):
        if conversation.active_tutor_session_id is None:
            return
        session = self.education.store.get_session(conversation.active_tutor_session_id)
        if session.status.value not in {"SOLVED", "ABANDONED"}:
            self.education.abandon(
                session.session_id,
                created_at=created_at,
                operation_id=operation_id,
            )
            self._observe(
                conversation,
                ProgressEventKind.EXERCISE_ABANDONED,
                created_at=created_at,
                operation_id=operation_id,
            )

    def _verify_progress_authority(self, event):
        conversation = self.conversations.get(event.conversation_id)
        if conversation.learner_id != event.learner_id:
            raise ValueError("cross-learner progress authority")
        session = self.education.store.get_session(event.tutor_session_id)
        entry = self.education.catalog.by_entry_hash(session.catalog_entry_hash)
        require_current(evaluate_entry_currentness(self.education.chemistry, entry))
        instance = self.education.store.get_artifact(
            session.exercise_hash, expected_kind="exercise_instance_internal"
        )
        if (
            session.catalog_entry_hash != event.catalog_entry_hash
            or instance.semantic_key_hash != event.semantic_key_hash
        ):
            raise ValueError("progress authority binding mismatch")
        expected_concepts = self.education.domain_runtime.concepts_for_exercise_family(
            entry.exercise_spec.family.value
        )
        if event.concept_ids != expected_concepts:
            raise ValueError(
                "progress concepts are not derived from the installed pack"
            )
        if (
            event.grading_result_hash
            and event.grading_result_hash not in session.grading_result_hashes
        ):
            raise ValueError("progress grading reference mismatch")
        authority_events = {
            item.event_hash: item
            for item in self.education.store.events(session.session_id)
        }
        if (
            not event.authority_hashes
            or event.authority_hashes[0] not in authority_events
        ):
            raise ValueError(
                "progress event lacks an exact educational event authority"
            )
        source = authority_events[event.authority_hashes[0]]
        expected_type = {
            ProgressEventKind.EXERCISE_PRESENTED: "SESSION_PRESENTED",
            ProgressEventKind.ANSWER_GRADED: "ANSWER_GRADED",
            ProgressEventKind.HINT_USED: "HINT_ISSUED",
            ProgressEventKind.SOLUTION_REVEALED: "SOLUTION_REVEALED",
            ProgressEventKind.EXERCISE_SOLVED: "ANSWER_GRADED",
            ProgressEventKind.EXERCISE_ABANDONED: "SESSION_ABANDONED",
        }.get(event.event_kind)
        if expected_type is not None and source.event_type != expected_type:
            raise ValueError("progress event kind disagrees with educational authority")
        if event.operation_id is not None and source.operation_id != event.operation_id:
            raise ValueError("progress and education operation IDs disagree")
        if event.observed_at != source.created_at:
            raise ValueError("progress timestamp is not authority-derived")
        if event.event_kind in {
            ProgressEventKind.ANSWER_GRADED,
            ProgressEventKind.EXERCISE_SOLVED,
        }:
            grading_hash = source.payload["grading_result_hash"]
            if (
                event.grading_result_hash != grading_hash
                or len(event.authority_hashes) < 2
                or event.authority_hashes[1] != grading_hash
            ):
                raise ValueError("progress grade is not authority-derived")
            grade = self.education.store.get_artifact(
                grading_hash, expected_kind="grading_result"
            )
            correct = grade.correctness_status in {
                GradingStatus.CORRECT,
                GradingStatus.CORRECT_EQUIVALENT_UNIT,
                GradingStatus.CORRECT_WITH_ACCEPTABLE_ROUNDING,
            }
            if event.correct is not correct:
                raise ValueError("progress correctness is not authority-derived")
        if event.event_kind is ProgressEventKind.HINT_USED:
            hint = self.education.store.get_artifact(
                source.payload["hint_hash"], expected_kind="hint"
            )
            if (
                event.hint_level != int(hint.level)
                or event.payload.hint_hash != hint.hint_hash
                or len(event.authority_hashes) < 2
                or event.authority_hashes[1] != hint.hint_hash
            ):
                raise ValueError("progress hint level is not authority-derived")
        if event.event_kind is ProgressEventKind.SOLUTION_REVEALED and (
            not event.solution_revealed
            or event.payload.explanation_hash != source.payload["explanation_hash"]
            or len(event.authority_hashes) < 2
            or event.authority_hashes[1] != source.payload["explanation_hash"]
        ):
            raise ValueError("solution progress disagrees with session authority")
        if (
            event.event_kind is ProgressEventKind.EXERCISE_ABANDONED
            and session.status.value != "ABANDONED"
        ):
            raise ValueError("abandoned progress lacks a valid session transition")

    def _dependency_snapshot(self):
        return (
            self.education.catalog.manifest.catalog_hash,
            self.education.chemistry.manifest["domain_manifest_hash"],
            self.education.chemistry.manifest["fact_memory_snapshot_hash"],
            self.education.chemistry.manifest["source_chain_hash"],
            *tuple(
                value
                for _, value in self.education.chemistry.registry.current_manifest_hashes()
            ),
            self.education.domain_runtime.pack_hash(),
        )

    def _concept_ids(self):
        return tuple(
            item.concept_id
            for item in self.education.domain_runtime.concept_graph().nodes
        )

    def _project(self, learner_id, events):
        return project_progress(learner_id, events, concept_ids=self._concept_ids())

    def _progress_is_current(self, events):
        try:
            for event in events:
                if event.event_kind is not ProgressEventKind.PROGRESS_RESET:
                    self._verify_progress_authority(event)
            return True
        except (KeyError, ValueError):
            return False

    def _recommend(self, conversation, projections, *, required):
        graph = self.education.domain_runtime.concept_graph()
        prerequisites: dict[str, tuple[str, ...]] = {}
        for concept in self._concept_ids():
            prerequisites[concept] = tuple(
                edge.target_concept_id
                for edge in graph.edges
                if edge.kind.value == "PREREQUISITE"
                and edge.source_concept_id == concept
            )
        recent = None
        events = self.progress.events(conversation.learner_id)
        if events:
            recent = events[-1].semantic_key_hash
        try:
            return recommend_exercise(
                conversation.learner_id,
                projections,
                self._catalog_candidates,
                recent_semantic_key=recent,
                concepts=self._concept_ids(),
                prerequisites=prerequisites,
            )
        except ValueError:
            if required:
                raise
            return None

    def _index_catalog_candidates(self):
        """Index the catalog whose full authority closure was verified on open."""
        candidates: dict[str, list[tuple[str, str]]] = {
            concept: [] for concept in self._concept_ids()
        }
        for entry in self.education.catalog.entries:
            try:
                concepts = self.education.domain_runtime.concepts_for_exercise_family(
                    entry.exercise_spec.family.value
                )
            except KeyError:
                continue
            for concept in concepts:
                candidates[concept].append(
                    (entry.entry_hash, entry.semantic_key.semantic_key_hash)
                )
        return {key: tuple(value) for key, value in candidates.items()}

    def _record(
        self,
        old,
        new,
        intent,
        original_text,
        response,
        *,
        created_at=None,
        pending_action=None,
        operation_id=None,
    ):
        verify_public_response(response)
        timestamp = created_at or utc_now()
        digest = response_hash(response)
        body = {
            "turn_id": "",
            "conversation_id": old.conversation_id,
            "sequence": len(old.turn_hashes) + 1,
            "speaker": Speaker.USER,
            "original_text_hash": content_hash(original_text),
            "parsed_intent": intent,
            "public_response_hash": digest,
            "previous_turn_hash": old.turn_hashes[-1] if old.turn_hashes else None,
            "created_at": timestamp,
            "operation_id": operation_id,
        }
        body["turn_id"] = f"conversation.turn.{content_hash(body)[:24]}"
        turn = ConversationTurn(**body, turn_hash=content_hash(body))
        final = self._change(
            new,
            turn_hashes=old.turn_hashes + (turn.turn_hash,),
            last_event_hash=turn.turn_hash,
            updated_at=timestamp,
        )
        response = replace(
            response, conversation_state=final.state.value, language=final.language
        )
        digest = response_hash(response)
        turn = replace(turn, public_response_hash=digest, turn_hash="")
        turn_body = asdict(turn)
        turn_body.pop("turn_hash")
        turn = replace(turn, turn_hash=content_hash(turn_body))
        final = self._change(
            final,
            turn_hashes=old.turn_hashes + (turn.turn_hash,),
            last_event_hash=turn.turn_hash,
        )
        self.conversations.append_interaction(
            old,
            final,
            turn,
            canonical_json(asdict(response)),
            digest,
            pending_action=pending_action,
        )
        return response

    def _change(self, conversation, **changes):
        provisional = replace(conversation, **changes, conversation_hash="")
        require_transition(
            conversation.state, provisional.state
        ) if provisional.state != conversation.state else None
        body = asdict(provisional)
        body.pop("conversation_hash")
        return replace(provisional, conversation_hash=content_hash(body))

    def _response(self, conversation, kind, text, **payload):
        return PublicConversationResponse(
            conversation_id=conversation.conversation_id,
            conversation_state=conversation.state.value,
            language=conversation.language,
            response_kind=kind,
            text=text,
            **payload,
        )

    @staticmethod
    def _formula(text: str) -> str:
        matches = re.findall(
            r"\b(?:[A-Z][a-z]?\d*)+(?:\((?:[A-Z][a-z]?\d*)+\)\d*)*\b", text
        )
        if not matches:
            raise ValueError("explanation requires one chemical formula")
        return matches[-1]


def _conversation_from_row(row):
    value = dict(row)
    value["state"] = ConversationState(value["state"])
    value["previous_active_state"] = ConversationState(value["previous_active_state"])
    value["turn_hashes"] = tuple(value["turn_hashes"])
    return TutorConversation(**value)


def _pending_action_from_row(row):
    value = dict(row)
    value["dependency_snapshot"] = tuple(value["dependency_snapshot"])
    value["prepared_authority_hashes"] = tuple(
        value.get("prepared_authority_hashes", ())
    )
    value["previous_state"] = ConversationState(value["previous_state"])
    value["status"] = PendingActionStatus(value["status"])
    return PendingAction(**value)


def _public_response_from_row(row):
    value = dict(row)
    if value.get("exercise") is not None:
        exercise = dict(value["exercise"])
        exercise["session"] = PublicTutorSessionHandle(**exercise["session"])
        exercise["learning_objectives"] = tuple(exercise["learning_objectives"])
        value["exercise"] = PublicExercise(**exercise)
    if value.get("submission") is not None:
        submission = dict(value["submission"])
        submission["session"] = PublicTutorSessionHandle(**submission["session"])
        submission["diagnoses"] = tuple(submission["diagnoses"])
        value["submission"] = PublicSubmissionResult(**submission)
    if value.get("hint") is not None:
        hint = dict(value["hint"])
        hint["session"] = PublicTutorSessionHandle(**hint["session"])
        value["hint"] = PublicHint(**hint)
    if value.get("solution") is not None:
        solution = dict(value["solution"])
        solution["session"] = PublicTutorSessionHandle(**solution["session"])
        value["solution"] = PublicSolution(**solution)
    if value.get("prepared_action") is not None:
        value["prepared_action"] = PublicPendingAction(**value["prepared_action"])
    return PublicConversationResponse(**value)


def _restore_pending_authority(payload, education):
    """Rehydrate the exact hash-bound prepared artifacts without re-routing."""
    try:
        response_row = dict(payload["prepared_response"])
        proposal_row = dict(payload["tool_proposal"])
        request_row = dict(payload["request"])
        decision_row = dict(payload["route_decision"])
        response_row["route_target"] = RouteTarget(response_row["route_target"])
        response_row["route_authority"] = RouteAuthority(
            response_row["route_authority"]
        )
        response_row["route_status"] = RouteStatus(response_row["route_status"])
        response_row["response_stage"] = ResponseStage(response_row["response_stage"])
        response_row["warnings"] = tuple(response_row["warnings"])
        prepared = UnifiedResponseEnvelope(**response_row)
        proposal = ToolCallProposal(**proposal_row)
        request_row["source_kind"] = RequestSourceKind(request_row["source_kind"])
        request = RequestEnvelope(**request_row)
        dependency_row = dict(decision_row["dependencies"])
        dependency_row["tool_implementation_manifest_hashes"] = tuple(
            tuple(item)
            for item in dependency_row["tool_implementation_manifest_hashes"]
        )
        decision_row["dependencies"] = DependencySnapshot(**dependency_row)
        decision_row["selected_target"] = RouteTarget(decision_row["selected_target"])
        decision_row["route_status"] = RouteStatus(decision_row["route_status"])
        decision_row["route_authority"] = RouteAuthority(
            decision_row["route_authority"]
        )
        decision_row["candidate_targets"] = tuple(
            RouteTarget(item) for item in decision_row["candidate_targets"]
        )
        decision_row["ambiguity_fields"] = tuple(decision_row["ambiguity_fields"])
        decision_row["required_next_action"] = NextAction(
            decision_row["required_next_action"]
        )
        decision = RouteDecision(**decision_row)
    except (KeyError, TypeError, ValueError):
        return None
    unified = education.chemistry.unified
    unified._requests[request.request_id] = request
    unified._decisions[decision.route_decision_hash] = decision
    unified._tool_proposals[proposal.proposal_hash] = proposal
    unified._responses[prepared.response_hash] = prepared
    return prepared, proposal
