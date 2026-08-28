"""Trusted orchestration for exact educational graphs, exercises, and sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.education.controlled import (
    parse_educational_request,
)
from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.exercise_generation import generate_exercise
from ai_brain.stage2.education.explanations import render_explanation
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import (
    EducationalRouteKind,
    ExerciseFamily,
    ExplanationMode,
    GradingStatus,
    HintLevel,
)
from ai_brain.stage2.education.persistence import EducationalSessionStore
from ai_brain.stage2.education.replay import replay_educational_session
from ai_brain.stage2.education.serialization import (
    grading_from_dict,
    graph_from_dict,
    instance_from_dict,
    spec_from_dict,
)
from ai_brain.stage2.education.sessions import apply_event, make_event, start_session
from ai_brain.stage2.facts.canonical import content_hash, utc_now


class EducationalService:
    def __init__(
        self,
        chemistry: ChemistryDomainService,
        store: EducationalSessionStore,
    ) -> None:
        self.chemistry = chemistry
        self.adapter = ChemistryEducationAdapter(chemistry)
        self.store = store

    @classmethod
    def open(cls, chemistry_root: Path, store_root: Path) -> EducationalService:
        return cls(
            ChemistryDomainService.open(chemistry_root),
            EducationalSessionStore.open_or_initialize(store_root),
        )

    def explain_tool(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        language: str,
        mode: ExplanationMode = ExplanationMode.FULL,
    ):
        result, graph = self.adapter.tool_graph(tool_id, arguments)
        explanation = render_explanation(graph, language=language, mode=mode)
        return result, graph, explanation

    def handle_controlled(
        self,
        text: str,
        *,
        language: str,
        session_id: str | None = None,
        seed: int = 0,
    ):
        route = parse_educational_request(text, language)
        if route.kind == EducationalRouteKind.EXPLAIN:
            result = self.explain_tool(
                "chemistry_molar_mass",
                {
                    "formula": route.payload["formula"],
                    "mode": "conventional",
                    "unit": "g/mol",
                    "significant_digits": 8,
                },
                language=language,
            )
        elif route.kind == EducationalRouteKind.GENERATE_EXERCISE:
            result = self.create_exercise(
                ExerciseFamily.MOLAR_MASS_SIMPLE,
                seed=seed,
                language=language,
                session_id=session_id,
            )
        elif route.kind == EducationalRouteKind.CHECK_ANSWER:
            if session_id is None:
                raise ValueError("checking an answer requires a tutor session")
            result = self.submit_answer(session_id, route.payload["answer"])
        elif route.kind == EducationalRouteKind.HINT:
            if session_id is None:
                raise ValueError("a hint requires a tutor session")
            result = self.hint(session_id)
        elif route.kind == EducationalRouteKind.SHOW_SOLUTION:
            if session_id is None:
                raise ValueError("a solution requires a tutor session")
            result = self.show_solution(session_id)
        else:
            result = None
        return route, result

    def create_exercise(
        self,
        family: ExerciseFamily,
        *,
        seed: int,
        language: str,
        difficulty: int | None = None,
        session_id: str | None = None,
        created_at: str | None = None,
    ):
        spec, instance, graph = generate_exercise(
            self.adapter,
            family,
            seed=seed,
            language=language,
            difficulty=difficulty,
        )
        self.store.save_artifact("exercise_spec", spec.spec_hash, spec)
        self.store.save_artifact("exercise_instance", instance.instance_hash, instance)
        self.store.save_artifact("derivation_graph", graph.graph_hash, graph)
        timestamp = created_at or utc_now()
        identity = (
            session_id
            or f"education.session.{content_hash({'exercise': instance.instance_hash, 'created_at': timestamp})[:24]}"
        )
        session, event = start_session(
            instance, session_id=identity, created_at=timestamp
        )
        self.store.create_session(session, event)
        return spec, instance, graph, session

    def submit_answer(
        self,
        session_id: str,
        raw_answer: Any,
        *,
        confirmed: bool = False,
        created_at: str | None = None,
    ):
        session, spec, instance, graph = self._load(session_id)
        timestamp = created_at or utc_now()
        answer = parse_student_answer(
            raw_answer,
            spec.accepted_answer_type,
            supported_symbols=set(self.chemistry.manifest["supported_elements"]),
            confirmed=confirmed,
        )
        self.store.save_artifact("student_answer", answer.answer_hash, answer)
        submitted = make_event(
            session_id,
            sequence=len(self.store.events(session_id)) + 1,
            event_type="ANSWER_SUBMITTED",
            payload={
                "student_answer_hash": answer.answer_hash,
                "submitted_answer": raw_answer,
            },
            previous_event_hash=session.last_event_hash,
            created_at=timestamp,
        )
        attempted = apply_event(session, submitted)
        self.store.append_event(session, attempted, submitted)
        grade = grade_answer(
            instance,
            answer,
            graph,
            attempt_id=f"education.attempt.{answer.answer_hash[:24]}",
            created_at=timestamp,
        )
        self.store.save_artifact("grading_result", grade.result_hash, grade)
        solved = grade.correctness_status in {
            GradingStatus.CORRECT,
            GradingStatus.CORRECT_EQUIVALENT_UNIT,
            GradingStatus.CORRECT_WITH_ACCEPTABLE_ROUNDING,
        }
        graded = make_event(
            session_id,
            sequence=len(self.store.events(session_id)) + 1,
            event_type="ANSWER_GRADED",
            payload={"grading_result_hash": grade.result_hash, "solved": solved},
            previous_event_hash=attempted.last_event_hash,
            created_at=timestamp,
        )
        current = apply_event(attempted, graded)
        self.store.append_event(attempted, current, graded)
        return answer, grade, current

    def hint(
        self,
        session_id: str,
        *,
        level: HintLevel | None = None,
        created_at: str | None = None,
    ):
        session, _, instance, graph = self._load(session_id)
        selected = level or HintLevel(min(5, len(session.hint_hashes) + 1))
        diagnoses = ()
        if session.grading_result_hashes:
            grade = grading_from_dict(
                self.store.get_artifact(
                    session.grading_result_hashes[-1], expected_kind="grading_result"
                )
            )
            diagnoses = grade.error_diagnoses
        hint = render_hint(
            build_hint_plan(instance.instance_id, graph),
            graph,
            selected,
            language=session.language,
            diagnoses=diagnoses,
        )
        self.store.save_artifact("hint", hint.hint_hash, hint)
        event = make_event(
            session_id,
            sequence=len(self.store.events(session_id)) + 1,
            event_type="HINT_ISSUED",
            payload={"hint_hash": hint.hint_hash, "level": int(selected)},
            previous_event_hash=session.last_event_hash,
            created_at=created_at or utc_now(),
        )
        current = apply_event(session, event)
        self.store.append_event(session, current, event)
        return hint, current

    def show_solution(self, session_id: str, *, created_at: str | None = None):
        session, _, _, graph = self._load(session_id)
        explanation = render_explanation(
            graph,
            language=session.language,
            mode=ExplanationMode.SOLUTION_AFTER_ATTEMPT,
            attempt_made=bool(session.attempt_hashes),
        )
        self.store.save_artifact(
            "explanation", explanation.explanation_hash, explanation
        )
        event = make_event(
            session_id,
            sequence=len(self.store.events(session_id)) + 1,
            event_type="SOLUTION_REVEALED",
            payload={"explanation_hash": explanation.explanation_hash},
            previous_event_hash=session.last_event_hash,
            created_at=created_at or utc_now(),
        )
        current = apply_event(session, event)
        self.store.append_event(session, current, event)
        return explanation, current

    def replay(self, session_id: str):
        return replay_educational_session(self.store, self.adapter, session_id)

    def verify(self):
        domain = self.chemistry.verify()
        sessions = self.store.verify()
        return {
            "status": "VERIFIED",
            "domain": domain,
            "educational_store": sessions,
            "trusted_imports_torch": False,
            "runtime_network": False,
        }

    def _load(self, session_id: str):
        session = self.store.get_session(session_id)
        instance = instance_from_dict(
            self.store.get_artifact(
                session.exercise_hash, expected_kind="exercise_instance"
            )
        )
        spec = spec_from_dict(
            self.store.get_artifact(
                instance.exercise_spec_hash, expected_kind="exercise_spec"
            )
        )
        graph = graph_from_dict(
            self.store.get_artifact(
                session.graph_hash, expected_kind="derivation_graph"
            )
        )
        return session, spec, instance, graph
