"""Trusted runtime orchestration over a verified precompiled catalog."""

from __future__ import annotations

import re
from dataclasses import asdict
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
from ai_brain.stage2.education.artifact_authority import (
    EducationalArtifactAuthorityVerifier,
)
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.currentness import (
    evaluate_dependency_currentness,
    evaluate_entry_currentness,
    require_current,
)
from ai_brain.stage2.education.exercise_generation import (
    instantiate_variant,
    present_exercise,
    public_exercise,
    verify_exercise_instance,
    verify_presented_exercise,
)
from ai_brain.stage2.education.explanations import (
    build_explanation_plan,
    render_check_explanation,
    render_explanation,
)
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import (
    EducationalRouteKind,
    EducationalRouteReceipt,
    ExerciseFamily,
    ExplanationArtifact,
    ExplanationMode,
    GradingStatus,
    HintLevel,
    PublicExplanation,
    PublicHint,
    PublicReplayStatus,
    PublicSolution,
    PublicSubmissionResult,
    PublicTutorSessionHandle,
)
from ai_brain.stage2.education.persistence import EducationalSessionStore
from ai_brain.stage2.education.replay import replay_educational_session
from ai_brain.stage2.education.sessions import apply_event, make_event, start_session
from ai_brain.stage2.facts.canonical import content_hash, utc_now

DEFAULT_CATALOG_PATH = Path("artifacts/education/m292/catalog_v3.json")


class EducationalExecutionMonitor:
    """Instance-local spy over the unchanged chemistry registry contract."""

    def __init__(self, registry) -> None:
        self.count = 0
        self.events: list[dict[str, str]] = []
        original = registry.execute

        def monitored(tool_id, arguments, **kwargs):
            result = original(tool_id, arguments, **kwargs)
            self.count += 1
            self.events.append(
                {
                    "tool_id": tool_id,
                    "argument_hash": content_hash(arguments),
                    "result_hash": result["result_hash"],
                }
            )
            return result

        registry.execute = monitored


class EducationalService:
    def __init__(
        self,
        chemistry: ChemistryDomainService,
        store: EducationalSessionStore,
        catalog: EducationalCatalogV2,
    ) -> None:
        self.chemistry = chemistry
        self.adapter = ChemistryEducationAdapter(chemistry)
        self.store = store
        self.catalog = catalog
        self.execution_monitor = EducationalExecutionMonitor(chemistry.registry)

    @classmethod
    def open(
        cls,
        chemistry_root: Path,
        store_root: Path,
        *,
        catalog_path: Path = DEFAULT_CATALOG_PATH,
    ) -> EducationalService:
        chemistry = ChemistryDomainService.open(chemistry_root)
        return cls(
            chemistry,
            EducationalSessionStore.open_or_initialize(store_root),
            EducationalCatalogV2.load(catalog_path, chemistry),
        )

    def explain_tool(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        language: str,
        mode: ExplanationMode = ExplanationMode.FULL,
    ):
        outcome = self._explain_tool_internal(
            tool_id, arguments, language=language, mode=mode
        )
        if isinstance(outcome, tuple) and isinstance(outcome[2], ExplanationArtifact):
            return PublicExplanation(
                status="CURRENT",
                language=language,
                mode=mode.value,
                text=_learner_text(outcome[2].text),
                confirmation_required=False,
            )
        return PublicExplanation(
            status="PREPARED",
            language=language,
            mode=mode.value,
            text=None,
            confirmation_required=True,
        )

    def _explain_tool_internal(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        language: str,
        mode: ExplanationMode = ExplanationMode.FULL,
    ):
        """Load an authority artifact or prepare an explicitly confirmed execution."""
        before = self.execution_monitor.count
        entry = self.catalog.find_tool(tool_id, arguments)
        if entry is not None:
            require_current(evaluate_entry_currentness(self.chemistry, entry))
            explanation = render_explanation(entry.graph, language=language, mode=mode)
            if self.execution_monitor.count != before:
                raise RuntimeError("precompiled explanation executed a chemistry tool")
            return entry.graph.source_result_artifact, entry.graph, explanation
        prepared = self.chemistry.prepare_tool(tool_id, arguments)
        if self.execution_monitor.count != before:
            raise RuntimeError("unconfirmed explanation executed a chemistry tool")
        return prepared

    def confirm_explanation(
        self,
        prepared,
        proposal,
        *,
        identity: str,
        language: str,
        mode: ExplanationMode = ExplanationMode.FULL,
    ):
        outcome = self._confirm_explanation_internal(
            prepared,
            proposal,
            identity=identity,
            language=language,
            mode=mode,
        )
        return PublicExplanation(
            status="CURRENT",
            language=language,
            mode=mode.value,
            text=_learner_text(outcome[2].text),
            confirmation_required=False,
        )

    def _confirm_explanation_internal(
        self,
        prepared,
        proposal,
        *,
        identity: str,
        language: str,
        mode: ExplanationMode = ExplanationMode.FULL,
    ):
        before = self.execution_monitor.count
        result, completed = self.chemistry.confirm_and_execute(
            prepared, proposal, identity=identity
        )
        if result is None:
            raise ValueError("confirmed chemistry explanation did not execute")
        if self.execution_monitor.count != before + 1:
            raise RuntimeError("confirmed explanation execution count is not one")
        graph = self.adapter.graph_from_completed_result(
            proposal.tool_id,
            proposal.typed_arguments,
            result.output,
            request_hash=result.request_hash,
            route_decision_hash=result.route_decision_hash,
            created_at=result.executed_at,
        )
        explanation = render_explanation(graph, language=language, mode=mode)
        return result.output, graph, explanation, completed

    def handle_controlled(
        self,
        text: str,
        *,
        language: str,
        session_id: str | None = None,
        seed: int = 0,
    ):
        return self._handle_controlled_internal(
            text,
            language=language,
            session_id=session_id,
            seed=seed,
        )[2]

    def _handle_controlled_internal(
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
        receipt = self._route_receipt(text, route, session_id, result)
        return route, receipt, result

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
        presented, session = self._create_exercise_internal(
            family,
            seed=seed,
            language=language,
            difficulty=difficulty,
            session_id=session_id,
            created_at=created_at,
        )
        return public_exercise(presented, session_status=session.status.value)

    def _create_exercise_internal(
        self,
        family: ExerciseFamily,
        *,
        seed: int,
        language: str,
        difficulty: int | None = None,
        session_id: str | None = None,
        created_at: str | None = None,
    ):
        before = self.execution_monitor.count
        entry = self.catalog.select(family, seed=seed, difficulty=difficulty)
        require_current(evaluate_entry_currentness(self.chemistry, entry))
        instance = instantiate_variant(
            entry.internal_instance,
            entry.exercise_spec,
            entry.graph,
            seed=seed,
            language=language,
        )
        verify_exercise_instance(instance, entry.exercise_spec, entry.graph)
        self.store.save_artifact(
            "exercise_spec", entry.exercise_spec.spec_hash, entry.exercise_spec
        )
        self.store.save_artifact(
            "exercise_instance_internal", instance.instance_hash, instance
        )
        self.store.save_artifact(
            "source_result",
            entry.graph.source_result_hash,
            entry.graph.source_result_artifact,
        )
        self.store.save_artifact(
            "compilation_receipt",
            entry.compilation_receipt.receipt_hash,
            entry.compilation_receipt,
        )
        self.store.save_artifact(
            "derivation_graph", entry.graph.graph_hash, entry.graph
        )
        timestamp = created_at or utc_now()
        identity = session_id or (
            "education.session."
            + content_hash(
                {"exercise": instance.instance_hash, "created_at": timestamp}
            )[:24]
        )
        session, event = start_session(
            instance, session_id=identity, created_at=timestamp
        )
        presented = present_exercise(instance, entry.exercise_spec, session_id=identity)
        verify_presented_exercise(presented)
        self.store.save_artifact(
            "presented_exercise", presented.presentation_hash, presented
        )
        self.store.create_session(session, event)
        if self.execution_monitor.count != before:
            raise RuntimeError("exercise presentation executed a chemistry tool")
        return presented, session

    def submit_answer(
        self,
        session_id: str,
        raw_answer: Any,
        *,
        confirmed: bool = False,
        created_at: str | None = None,
    ):
        _, grade, check, current = self._submit_answer_internal(
            session_id,
            raw_answer,
            confirmed=confirmed,
            created_at=created_at,
        )
        return PublicSubmissionResult(
            parse_status=grade.parse_status.value,
            status=grade.correctness_status.value,
            score=grade.score,
            maximum_score=grade.maximum_score,
            diagnoses=tuple(item.code.value for item in grade.error_diagnoses),
            feedback=_learner_text(check.text),
            session=PublicTutorSessionHandle(
                session_id=current.session_id, status=current.status.value
            ),
        )

    def _submit_answer_internal(
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
            payload={"student_answer_hash": answer.answer_hash},
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
        check = render_check_explanation(
            graph, grade, language=session.language
        )
        self.store.save_artifact("explanation", check.explanation_hash, check)
        solved = grade.correctness_status in {
            GradingStatus.CORRECT,
            GradingStatus.CORRECT_EQUIVALENT_UNIT,
            GradingStatus.CORRECT_WITH_ACCEPTABLE_ROUNDING,
        }
        graded = make_event(
            session_id,
            sequence=len(self.store.events(session_id)) + 1,
            event_type="ANSWER_GRADED",
            payload={
                "grading_result_hash": grade.result_hash,
                "check_explanation_hash": check.explanation_hash,
                "solved": solved,
            },
            previous_event_hash=attempted.last_event_hash,
            created_at=timestamp,
        )
        current = apply_event(attempted, graded)
        self.store.append_event(attempted, current, graded)
        return answer, grade, check, current

    def hint(
        self,
        session_id: str,
        *,
        level: HintLevel | None = None,
        created_at: str | None = None,
    ):
        artifact, current = self._hint_internal(
            session_id, level=level, created_at=created_at
        )
        return PublicHint(
            level=int(artifact.level),
            text=_learner_text(artifact.text),
            session=PublicTutorSessionHandle(
                session_id=current.session_id, status=current.status.value
            ),
        )

    def _hint_internal(
        self,
        session_id: str,
        *,
        level: HintLevel | None = None,
        created_at: str | None = None,
    ):
        session, _, instance, graph = self._load(session_id)
        selected = level or HintLevel(min(5, len(session.hint_hashes) + 1))
        grading = None
        if session.grading_result_hashes:
            grading = self.store.get_artifact(
                session.grading_result_hashes[-1], expected_kind="grading_result"
            )
        plan = build_hint_plan(instance.instance_id, graph, grading=grading)
        self.store.save_artifact("hint_plan", plan.plan_hash, plan)
        hint = render_hint(
            plan,
            graph,
            selected,
            language=session.language,
            grading=grading,
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
        artifact, current = self._show_solution_internal(
            session_id, created_at=created_at
        )
        return PublicSolution(
            text=_learner_text(artifact.text),
            session=PublicTutorSessionHandle(
                session_id=current.session_id, status=current.status.value
            ),
        )

    def _show_solution_internal(
        self, session_id: str, *, created_at: str | None = None
    ):
        session, _, _, graph = self._load(session_id)
        plan = build_explanation_plan(
            graph,
            language=session.language,
            mode=ExplanationMode.SOLUTION_AFTER_ATTEMPT,
        )
        explanation = render_explanation(
            graph,
            language=session.language,
            mode=ExplanationMode.SOLUTION_AFTER_ATTEMPT,
            attempt_made=bool(session.attempt_hashes),
            session_id=session.session_id,
            session_state_hash=session.session_hash,
        )
        self.store.save_artifact("explanation_plan", plan.plan_hash, plan)
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
        status = self._replay_internal(session_id)
        return PublicReplayStatus(
            session_id=session_id,
            status=status["status"],
            session_status=status.get("session_status"),
        )

    def _replay_internal(self, session_id: str):
        return replay_educational_session(self.store, self.adapter, session_id)

    def verify(self):
        authority = EducationalArtifactAuthorityVerifier(self).verify()
        return {
            "status": "AUTHORITY_VERIFIED",
            "domain": self.chemistry.verify(),
            "catalog": self.catalog.verify(self.chemistry),
            "educational_store_structural": authority["structural"],
            "educational_store_authority": authority,
            "trusted_imports_torch": False,
            "runtime_network": False,
        }

    def backup(self, target: Path) -> dict[str, Any]:
        verification = self.verify()
        return {
            "verification": verification,
            "backup": self.store.backup(target),
        }

    @classmethod
    def restore(
        cls,
        chemistry_root: Path,
        backup: Path,
        target: Path,
        *,
        catalog_path: Path = DEFAULT_CATALOG_PATH,
    ) -> tuple[EducationalService, dict[str, Any]]:
        EducationalSessionStore.restore(backup, target)
        service = cls.open(chemistry_root, target, catalog_path=catalog_path)
        return service, service.verify()

    def _load(self, session_id: str):
        session = self.store.get_session(session_id)
        instance = self.store.get_artifact(
            session.exercise_hash, expected_kind="exercise_instance_internal"
        )
        spec = self.store.get_artifact(
            instance.exercise_spec_hash, expected_kind="exercise_spec"
        )
        graph = self.store.get_artifact(
            session.graph_hash, expected_kind="derivation_graph"
        )
        receipt = self.store.get_artifact(
            instance.compilation_receipt_hash,
            expected_kind="compilation_receipt",
        )
        require_current(
            evaluate_dependency_currentness(
                self.chemistry, graph, receipt, instance, spec
            )
        )
        verify_exercise_instance(instance, spec, graph)
        self.adapter.verify_graph(graph)
        return session, spec, instance, graph

    def _route_receipt(self, text, route, session_id, result):
        presented_hash = None
        prepared_hash = None
        if route.kind == EducationalRouteKind.GENERATE_EXERCISE and result:
            session_id = result.session.session_id
            matches = tuple(
                item
                for item in self.store.artifacts("presented_exercise")
                if item.session_id == session_id
            )
            if len(matches) == 1:
                presented_hash = matches[0].presentation_hash
        body = {
            "original_request_hash": content_hash(text),
            "controlled_parser_version": "educational_controlled_v2",
            "route_kind": route.kind,
            "session_id": session_id,
            "presented_exercise_hash": presented_hash,
            "prepared_response_hash": prepared_hash,
            "requested_action": route.kind.value,
            "dependency_snapshot": (
                self.catalog.manifest.catalog_hash,
                self.chemistry.manifest["domain_manifest_hash"],
            ),
            "created_at": utc_now(),
        }
        receipt = EducationalRouteReceipt(**body, receipt_hash=content_hash(body))
        verify_educational_route_receipt(receipt)
        return receipt


def verify_educational_route_receipt(receipt: EducationalRouteReceipt) -> None:
    body = asdict(receipt)
    digest = body.pop("receipt_hash")
    if content_hash(body) != digest:
        raise ValueError("educational route receipt hash mismatch")
    if (
        receipt.controlled_parser_version != "educational_controlled_v2"
        or receipt.requested_action != receipt.route_kind.value
        or len(receipt.dependency_snapshot) != 2
    ):
        raise ValueError("educational route receipt semantic mismatch")
    if receipt.route_kind == EducationalRouteKind.GENERATE_EXERCISE:
        if not receipt.session_id or not receipt.presented_exercise_hash:
            raise ValueError("exercise route receipt lacks its public binding")
    elif receipt.presented_exercise_hash is not None:
        raise ValueError("non-exercise route receipt has a presentation binding")
    if (
        receipt.route_kind
        in {
            EducationalRouteKind.CHECK_ANSWER,
            EducationalRouteKind.HINT,
            EducationalRouteKind.SHOW_SOLUTION,
        }
        and not receipt.session_id
    ):
        raise ValueError("session route receipt lacks its session binding")


def _learner_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith(("Graph:", "Result:", "Граф:", "Результат:")):
            continue
        line = re.sub(r"^\[[^]]+\]\s*", "", line)
        line = re.sub(r"\b[0-9a-f]{64}\b", "[verified]", line)
        lines.append(line)
    return "\n".join(lines)
