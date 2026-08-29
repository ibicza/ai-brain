"""Service-aware semantic verification of persisted educational closures."""

from __future__ import annotations

from ai_brain.stage2.education.catalog_anchor import verify_instance_catalog_anchor
from ai_brain.stage2.education.compilation_receipts import (
    verify_compilation_receipt_structure,
)
from ai_brain.stage2.education.currentness import (
    evaluate_dependency_currentness,
)
from ai_brain.stage2.education.exercise_generation import (
    verify_exercise_instance,
    verify_presented_exercise_binding,
)
from ai_brain.stage2.education.explanations import (
    render_check_explanation,
    render_explanation_plan,
)
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import (
    EducationalHistoryStatus,
    EducationalReplayStatus,
    ExplanationMode,
    GradingStatus,
)
from ai_brain.stage2.education.sessions import apply_event, start_session


class EducationalArtifactAuthorityVerifier:
    """Verify semantic meaning with explicit chemistry-service authority."""

    def __init__(self, service) -> None:
        self.service = service
        self.store = service.store

    def verify(self) -> dict[str, object]:
        structural = self.store.verify()
        verified = 0
        referenced = {
            kind: set()
            for kind in (
                "presented_exercise",
                "student_answer",
                "grading_result",
                "hint_plan",
                "hint",
                "explanation_plan",
                "explanation",
            )
        }
        currentness = []
        for session_id in self.store.session_ids():
            currentness.append(self._verify_session(session_id))
            self._collect_session_references(session_id, referenced)
            verified += 1
        identity_fields = {
            "presented_exercise": "presentation_hash",
            "student_answer": "answer_hash",
            "grading_result": "result_hash",
            "hint_plan": "plan_hash",
            "hint": "hint_hash",
            "explanation_plan": "plan_hash",
            "explanation": "explanation_hash",
        }
        for kind, field in identity_fields.items():
            actual = {getattr(item, field) for item in self.store.artifacts(kind)}
            if actual != referenced[kind]:
                raise ValueError(f"orphaned or unreferenced authority artifact: {kind}")
        return {
            "status": "AUTHORITY_VERIFIED",
            "history_status": EducationalHistoryStatus.HISTORY_VALID.value,
            "current_authority_status": (
                EducationalHistoryStatus.CURRENT.value
                if all(item is EducationalReplayStatus.CURRENT for item in currentness)
                else EducationalHistoryStatus.STALE_WITH_HISTORY_VALID.value
            ),
            "current_session_count": sum(
                item is EducationalReplayStatus.CURRENT for item in currentness
            ),
            "stale_session_count": sum(
                item is not EducationalReplayStatus.CURRENT for item in currentness
            ),
            "session_currentness": tuple(item.value for item in currentness),
            "session_count": verified,
            "structural": structural,
        }

    def _collect_session_references(self, session_id: str, referenced) -> None:
        presented = tuple(
            item
            for item in self.store.artifacts("presented_exercise")
            if item.session_id == session_id
        )
        referenced["presented_exercise"].add(presented[0].presentation_hash)
        for event in self.store.events(session_id):
            if event.event_type == "ANSWER_SUBMITTED":
                referenced["student_answer"].add(event.payload["student_answer_hash"])
            elif event.event_type == "ANSWER_GRADED":
                referenced["grading_result"].add(event.payload["grading_result_hash"])
                referenced["explanation"].add(event.payload["check_explanation_hash"])
            elif event.event_type == "HINT_ISSUED":
                hint_hash = event.payload["hint_hash"]
                referenced["hint"].add(hint_hash)
                hint = self.store.get_artifact(hint_hash, expected_kind="hint")
                referenced["hint_plan"].add(hint.plan_hash)
            elif event.event_type == "SOLUTION_REVEALED":
                explanation_hash = event.payload["explanation_hash"]
                referenced["explanation"].add(explanation_hash)
                explanation = self.store.get_artifact(
                    explanation_hash, expected_kind="explanation"
                )
                referenced["explanation_plan"].add(explanation.plan_hash)

    def _verify_session(self, session_id: str) -> EducationalReplayStatus:
        stored = self.store.get_session(session_id)
        instance = self.store.get_artifact(
            stored.exercise_hash, expected_kind="exercise_instance_internal"
        )
        spec = self.store.get_artifact(
            instance.exercise_spec_hash, expected_kind="exercise_spec"
        )
        graph = self.store.get_artifact(
            stored.graph_hash, expected_kind="derivation_graph"
        )
        receipt = self.store.get_artifact(
            instance.compilation_receipt_hash, expected_kind="compilation_receipt"
        )
        source = self.store.get_artifact(
            graph.source_result_hash, expected_kind="source_result"
        )
        if source != graph.source_result_artifact:
            raise ValueError("source result is not the graph authority")
        entry = self.service.catalog.by_entry_hash(stored.catalog_entry_hash)
        if (
            entry.exercise_spec != spec
            or entry.graph != graph
            or entry.compilation_receipt != receipt
        ):
            raise ValueError("session authority differs from its catalog anchor")
        verify_instance_catalog_anchor(instance, entry)
        verify_compilation_receipt_structure(receipt)
        verify_derivation_graph(graph, expected_source_result=source)
        currentness = evaluate_dependency_currentness(
            self.service.chemistry, graph, receipt, instance, spec
        )
        verify_exercise_instance(instance, spec, graph)

        presented = tuple(
            item
            for item in self.store.artifacts("presented_exercise")
            if item.session_id == session_id
        )
        if len(presented) != 1:
            raise ValueError("session lacks one exact presented exercise")
        verify_presented_exercise_binding(
            presented[0], instance, spec, session_id=session_id
        )

        events = self.store.events(session_id)
        if not events:
            raise ValueError("session lacks events")
        state, first = start_session(
            instance,
            session_id=session_id,
            created_at=events[0].created_at,
            operation_id=events[0].operation_id,
        )
        if events[0] != first:
            raise ValueError("presentation event is not reproducible")
        for event in events[1:]:
            if event.event_type == "ANSWER_SUBMITTED":
                self.store.get_artifact(
                    event.payload["student_answer_hash"],
                    expected_kind="student_answer",
                )
            elif event.event_type == "ANSWER_GRADED":
                self._verify_grade(event, state, instance, graph)
            elif event.event_type == "HINT_ISSUED":
                self._verify_hint(event, state, instance, graph)
            elif event.event_type == "SOLUTION_REVEALED":
                self._verify_solution(event, state, graph)
            state = apply_event(state, event)
        if state != stored:
            raise ValueError("authority replay does not reproduce tutor session")
        return currentness.status

    def _verify_grade(self, event, state, instance, graph) -> None:
        if not state.attempt_hashes:
            raise ValueError("grade lacks a preceding answer")
        answer = self.store.get_artifact(
            state.attempt_hashes[-1], expected_kind="student_answer"
        )
        grade = self.store.get_artifact(
            event.payload["grading_result_hash"], expected_kind="grading_result"
        )
        expected = grade_answer(
            instance,
            answer,
            graph,
            attempt_id=f"education.attempt.{answer.answer_hash[:24]}",
            created_at=event.created_at,
        )
        if grade != expected:
            raise ValueError("grading result is not reproducible")
        solved = grade.correctness_status in {
            GradingStatus.CORRECT,
            GradingStatus.CORRECT_EQUIVALENT_UNIT,
            GradingStatus.CORRECT_WITH_ACCEPTABLE_ROUNDING,
        }
        if event.payload.get("solved") is not solved:
            raise ValueError("grading event solved flag is not reproducible")
        check = self.store.get_artifact(
            event.payload["check_explanation_hash"], expected_kind="explanation"
        )
        if check != render_check_explanation(graph, grade, language=state.language):
            raise ValueError("check explanation is not grading-derived")

    def _verify_hint(self, event, state, instance, graph) -> None:
        hint = self.store.get_artifact(event.payload["hint_hash"], expected_kind="hint")
        grading = (
            self.store.get_artifact(
                state.grading_result_hashes[-1], expected_kind="grading_result"
            )
            if state.grading_result_hashes
            else None
        )
        plan = self.store.get_artifact(hint.plan_hash, expected_kind="hint_plan")
        expected_plan = build_hint_plan(instance.instance_id, graph, grading=grading)
        if plan != expected_plan:
            raise ValueError("hint plan is not grading-derived")
        expected = render_hint(
            plan, graph, hint.level, language=state.language, grading=grading
        )
        if hint != expected or event.payload.get("level") != int(hint.level):
            raise ValueError("hint artifact is not reproducible")

    def _verify_solution(self, event, state, graph) -> None:
        artifact = self.store.get_artifact(
            event.payload["explanation_hash"], expected_kind="explanation"
        )
        if artifact.mode is not ExplanationMode.SOLUTION_AFTER_ATTEMPT:
            raise ValueError("solution event references another explanation mode")
        plan = self.store.get_artifact(
            artifact.plan_hash, expected_kind="explanation_plan"
        )
        expected = render_explanation_plan(
            plan,
            graph,
            session_id=state.session_id,
            session_state_hash=state.session_hash,
        )
        if artifact != expected or not state.attempt_hashes:
            raise ValueError("solution artifact lacks exact attempt/session authority")
