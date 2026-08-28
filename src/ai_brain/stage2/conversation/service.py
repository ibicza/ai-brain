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
    PendingActionStatus,
    PublicConversationResponse,
    Speaker,
    TutorConversation,
)
from ai_brain.stage2.conversation.pending_actions import (
    authorize_pending,
    prepare_pending_action,
    public_pending,
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
)
from ai_brain.stage2.facts.canonical import canonical_json, content_hash, utc_now
from ai_brain.stage2.progress.concepts import CONCEPTS
from ai_brain.stage2.progress.events import make_progress_event
from ai_brain.stage2.progress.models import ProgressEventKind
from ai_brain.stage2.progress.persistence import LearnerProgressStore
from ai_brain.stage2.progress.projection import project_progress
from ai_brain.stage2.progress.rendering import render_progress_summary

FAMILY_CONCEPTS = {
    ExerciseFamily.FACT_RETRIEVAL: ("ELEMENT_IDENTITY",),
    ExerciseFamily.FORMULA_COMPOSITION: (
        "FORMULA_PARSING",
        "SUBSCRIPT_COUNTING",
        "FORMULA_COMPOSITION",
    ),
    ExerciseFamily.MOLAR_MASS_SIMPLE: (
        "ATOMIC_WEIGHT_SINGLE",
        "FORMULA_PARSING",
        "MOLAR_MASS_SIMPLE",
    ),
    ExerciseFamily.MOLAR_MASS_GROUPED: ("GROUP_MULTIPLIER", "MOLAR_MASS_GROUPED"),
    ExerciseFamily.MASS_AMOUNT: ("MASS_TO_MOLES", "MOLES_TO_MASS", "UNIT_DIMENSION"),
    ExerciseFamily.AMOUNT_ENTITIES: ("MOLES_TO_FORMULA_ENTITIES", "UNIT_DIMENSION"),
}


class ConversationalTutorService:
    def __init__(
        self,
        education,
        conversations: ConversationStore,
        progress: LearnerProgressStore,
    ) -> None:
        self.education = education
        self.conversations = conversations
        self.progress = progress
        self.progress.authority_check = self._verify_progress_authority

    @classmethod
    def open(
        cls, education, conversation_root: Path, progress_root: Path
    ) -> ConversationalTutorService:
        return cls(
            education,
            ConversationStore.open_or_initialize(conversation_root),
            LearnerProgressStore.open_or_initialize(progress_root),
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
        outcome = self._execute(working, parsed, text, created_at=created_at)
        new, response = outcome[:2]
        pending_action = outcome[2] if len(outcome) == 3 else None
        return self._record(
            conversation,
            new,
            parsed.intent,
            text,
            response,
            created_at=created_at,
            pending_action=pending_action,
        )

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
        executed = authorize_pending(
            action,
            learner_id=conversation.learner_id,
            conversation_id=conversation_id,
            language=conversation.language,
            dependency_snapshot=self._dependency_snapshot(),
            now=created_at,
        )
        if action.action_kind != "EXPLAIN_MOLAR_MASS":
            raise ValueError("unsupported pending action kind")
        # Consume before external execution: a crash can lose an action, never replay it.
        self.conversations.replace_pending(action, executed)
        _, prepared, proposal = self.education.chemistry.prepare_tool(
            "chemistry_molar_mass", action.payload
        )
        result = self.education.confirm_explanation(
            prepared,
            proposal,
            identity=conversation.learner_id,
            language=conversation.language,
            mode=ExplanationMode.FULL,
        )
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
        return render_progress_summary(
            project_progress(
                conversation.learner_id, self.progress.events(conversation.learner_id)
            )
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
        last = events[-1]
        event = make_progress_event(
            learner_id=learner_id,
            conversation_id=last.conversation_id,
            tutor_session_id=last.tutor_session_id,
            catalog_entry_hash=last.catalog_entry_hash,
            semantic_key_hash=last.semantic_key_hash,
            concept_ids=tuple(CONCEPTS),
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

    def _execute(self, conversation, parsed, raw_text, *, created_at=None):
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
            self._abandon_if_needed(conversation, created_at=timestamp)
            seed = len(conversation.turn_hashes)
            family = ExerciseFamily(parsed.payload.get("family", "MOLAR_MASS_SIMPLE"))
            exercise = self.education.create_exercise(
                family, seed=seed, language=language
            )
            new = self._change(
                conversation,
                state=ConversationState.EXERCISE_ACTIVE,
                active_tutor_session_id=exercise.session.session_id,
                updated_at=timestamp,
            )
            self._observe(
                new, ProgressEventKind.EXERCISE_PRESENTED, created_at=timestamp
            )
            return new, self._response(
                new,
                "EXERCISE",
                "Решите задачу." if language == "ru" else "Solve this exercise.",
                exercise=exercise,
            )
        if intent is ConversationIntent.SUBMIT_ANSWER:
            submission = self.education.submit_answer(
                conversation.active_tutor_session_id, parsed.payload["text"]
            )
            self._observe(
                conversation,
                ProgressEventKind.ANSWER_GRADED,
                correct=submission.status.startswith("CORRECT"),
                grading=True,
                created_at=timestamp,
            )
            if submission.status.startswith("CORRECT"):
                self._observe(
                    conversation,
                    ProgressEventKind.EXERCISE_SOLVED,
                    correct=True,
                    grading=True,
                    created_at=timestamp,
                )
            return conversation, self._response(
                conversation, "SUBMISSION", submission.feedback, submission=submission
            )
        if intent is ConversationIntent.REQUEST_HINT:
            hint = self.education.hint(conversation.active_tutor_session_id)
            self._observe(
                conversation,
                ProgressEventKind.HINT_USED,
                hint_level=hint.level,
                created_at=timestamp,
            )
            return conversation, self._response(
                conversation, "HINT", hint.text, hint=hint
            )
        if intent is ConversationIntent.REQUEST_SOLUTION:
            solution = self.education.show_solution(
                conversation.active_tutor_session_id
            )
            self._observe(
                conversation,
                ProgressEventKind.SOLUTION_REVEALED,
                solution=True,
                created_at=timestamp,
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
            outcome = self.education.explain_tool(
                "chemistry_molar_mass", arguments, language=language
            )
            if not outcome.confirmation_required:
                return conversation, self._response(
                    conversation, "EXPLANATION", outcome.text or ""
                )
            action = prepare_pending_action(
                learner_id=conversation.learner_id,
                conversation_id=conversation.conversation_id,
                action_kind="EXPLAIN_MOLAR_MASS",
                request_hash=content_hash(raw_text),
                language=language,
                payload=arguments,
                dependency_snapshot=self._dependency_snapshot(),
                previous_state=conversation.state,
                created_at=timestamp,
            )
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
            self._abandon_if_needed(conversation, created_at=timestamp)
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
        concepts = FAMILY_CONCEPTS.get(spec.family, (CONCEPTS[0],))
        grading_hash = session.grading_result_hashes[-1] if grading else None
        prior_session_events = self.education.store.events(session.session_id)
        hints = sum(item.event_type == "HINT_ISSUED" for item in prior_session_events)
        revealed = solution or any(
            item.event_type == "SOLUTION_REVEALED" for item in prior_session_events
        )
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
            observed_at=created_at,
        )
        self.progress.append(event, authority_check=self._verify_progress_authority)

    def _abandon_if_needed(self, conversation, *, created_at):
        if conversation.active_tutor_session_id is None:
            return
        session = self.education.store.get_session(conversation.active_tutor_session_id)
        if session.status.value not in {"SOLVED", "ABANDONED"}:
            self._observe(
                conversation,
                ProgressEventKind.EXERCISE_ABANDONED,
                created_at=created_at,
            )

    def _verify_progress_authority(self, event):
        conversation = self.conversations.get(event.conversation_id)
        if conversation.learner_id != event.learner_id:
            raise ValueError("cross-learner progress authority")
        session, _, instance, _ = self.education._load(event.tutor_session_id)
        if (
            session.catalog_entry_hash != event.catalog_entry_hash
            or instance.semantic_key_hash != event.semantic_key_hash
        ):
            raise ValueError("progress authority binding mismatch")
        if (
            event.grading_result_hash
            and event.grading_result_hash not in session.grading_result_hashes
        ):
            raise ValueError("progress grading reference mismatch")

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
        )

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
