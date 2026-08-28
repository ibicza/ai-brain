"""M-29.2 hardening acceptance over public and authority-aware boundaries."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.education import replay as replay_module
from ai_brain.stage2.education import service as service_module
from ai_brain.stage2.education.acceptance_v2 import run_m291_acceptance
from ai_brain.stage2.education.artifact_authority import (
    EducationalArtifactAuthorityVerifier,
)
from ai_brain.stage2.education.compilation_receipts import (
    verify_compilation_receipt,
)
from ai_brain.stage2.education.currentness import (
    EducationalCurrentnessResult,
    EducationalIntegrityError,
)
from ai_brain.stage2.education.exercise_generation import (
    instantiate_variant,
    present_exercise,
    public_exercise,
    verify_presented_exercise_binding,
)
from ai_brain.stage2.education.explanations import (
    render_explanation,
    verify_explanation,
)
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.hints import render_hint
from ai_brain.stage2.education.models import (
    EducationalReplayStatus,
    ExerciseFamily,
    ExplanationMode,
    GradingStatus,
    HintLevel,
)
from ai_brain.stage2.education.sessions import apply_event, start_session
from ai_brain.stage2.facts.canonical import content_hash


def run_m292_acceptance(service, fixture_path: Path) -> dict:
    prior = run_m291_acceptance(service, fixture_path)
    currentness = _currentness_action_matrix(service)
    artifacts = _artifact_semantics(service)
    public = _public_boundary(service.catalog)
    verification = service.verify()
    splits = _split_summary(service.catalog)
    diagnosis = prior["diagnosis"]
    passed = all(
        (
            prior["status"] == "PASS",
            currentness["wrong_status"] == 0,
            currentness["mutating_rejections"] == 0,
            currentness["hidden_executions"] == 0,
            artifacts["accepted_semantic_tampers"] == 0,
            public["leaks"] == 0,
            splits["invalid_manifests"] == 0,
            diagnosis["wrong_confident_diagnosis"] == 0,
            diagnosis["wrong_targeted_hints"] == 0,
            diagnosis["grading_status_mismatch_count"] == 0,
            verification["educational_store_structural"]["status"]
            == "STRUCTURALLY_VERIFIED",
            verification["educational_store_authority"]["status"]
            == "AUTHORITY_VERIFIED",
        )
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "prior_m291": prior,
        "currentness_action_matrix": currentness,
        "artifact_semantics": artifacts,
        "public_boundary": public,
        "splits": splits,
        "diagnosis": diagnosis,
        "full_verification": verification,
        "operation_mutations": {
            "cases": prior["graph"]["cases_by_category"]["operation"],
            "accepted": prior["graph"]["accepted_by_category"]["operation"],
        },
        "content_policy_added": False,
        "m30_implemented": False,
    }


def _currentness_action_matrix(service) -> dict:
    session_id = "m292-currentness-matrix"
    service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=2_922,
        language="en",
        session_id=session_id,
        created_at="2026-08-28T02:00:00Z",
    )
    service.submit_answer(
        session_id,
        "0 g/mol",
        created_at="2026-08-28T02:01:00Z",
    )
    entry = service.catalog.select(ExerciseFamily.MOLAR_MASS_SIMPLE, seed=2_922)
    categories = {
        "domain": EducationalReplayStatus.STALE_DOMAIN,
        "fact_memory": EducationalReplayStatus.STALE_FACT_MEMORY,
        "source_chain": EducationalReplayStatus.STALE_SOURCE_CHAIN,
        "tool": EducationalReplayStatus.STALE_TOOL,
        "claim": EducationalReplayStatus.STALE_CLAIM,
        "evidence": EducationalReplayStatus.STALE_EVIDENCE,
        "source": EducationalReplayStatus.STALE_SOURCE,
        "upstream_source": EducationalReplayStatus.STALE_UPSTREAM_SOURCE,
        "compilation_receipt": EducationalReplayStatus.STALE_COMPILATION_RECEIPT,
        "answer_key_graph": EducationalReplayStatus.STALE_ANSWER_KEY,
    }
    actions = {
        "precompiled_explain": lambda: service.explain_tool(
            entry.compilation_receipt.tool_id,
            entry.compilation_receipt.canonical_arguments,
            language="en",
        ),
        "present": lambda: service.create_exercise(
            ExerciseFamily.MOLAR_MASS_SIMPLE, seed=2_923, language="en"
        ),
        "submit": lambda: service.submit_answer(session_id, "0 g/mol"),
        "hint": lambda: service.hint(session_id),
        "solution": lambda: service.show_solution(session_id),
        "replay": lambda: service._replay_internal(session_id),
    }
    original_entry = service_module.evaluate_entry_currentness
    original_dependency = service_module.evaluate_dependency_currentness
    original_replay = replay_module.evaluate_dependency_currentness
    wrong = 0
    mutations = 0
    before_executions = service.execution_monitor.count
    results = {}
    try:
        for category, expected in categories.items():
            current = EducationalCurrentnessResult(expected)
            service_module.evaluate_entry_currentness = lambda *args, r=current: r
            service_module.evaluate_dependency_currentness = lambda *args, r=current: r
            replay_module.evaluate_dependency_currentness = lambda *args, r=current: r
            results[category] = {}
            for name, action in actions.items():
                before = _store_state(service, session_id)
                observed = None
                try:
                    value = action()
                    if name == "replay":
                        observed = value["status"]
                except EducationalIntegrityError as error:
                    observed = error.status.value
                if observed != expected.value:
                    wrong += 1
                if _store_state(service, session_id) != before:
                    mutations += 1
                results[category][name] = observed
    finally:
        service_module.evaluate_entry_currentness = original_entry
        service_module.evaluate_dependency_currentness = original_dependency
        replay_module.evaluate_dependency_currentness = original_replay
    return {
        "case_count": len(categories) * len(actions),
        "categories": results,
        "wrong_status": wrong,
        "mutating_rejections": mutations,
        "hidden_executions": service.execution_monitor.count - before_executions,
    }


def _artifact_semantics(service) -> dict:
    session_id = "m292-artifact-acceptance"
    service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=2_924,
        language="en",
        session_id=session_id,
        created_at="2026-08-28T03:00:00Z",
    )
    service.submit_answer(session_id, "0 g/mol", created_at="2026-08-28T03:01:00Z")
    service.hint(
        session_id,
        level=HintLevel.ORIENT,
        created_at="2026-08-28T03:02:00Z",
    )
    service.show_solution(session_id, created_at="2026-08-28T03:03:00Z")
    stored = service.store.get_session(session_id)
    instance = service.store.get_artifact(
        stored.exercise_hash, expected_kind="exercise_instance_internal"
    )
    spec = service.store.get_artifact(
        instance.exercise_spec_hash, expected_kind="exercise_spec"
    )
    graph = service.store.get_artifact(
        stored.graph_hash, expected_kind="derivation_graph"
    )
    receipt = service.store.get_artifact(
        instance.compilation_receipt_hash, expected_kind="compilation_receipt"
    )
    presented = next(
        item
        for item in service.store.artifacts("presented_exercise")
        if item.session_id == session_id
    )
    grade = service.store.get_artifact(
        stored.grading_result_hashes[-1], expected_kind="grading_result"
    )
    answer = service.store.get_artifact(
        stored.attempt_hashes[-1], expected_kind="student_answer"
    )
    hint = service.store.get_artifact(stored.hint_hashes[-1], expected_kind="hint")
    plan = service.store.get_artifact(hint.plan_hash, expected_kind="hint_plan")
    check = next(
        item
        for item in service.store.artifacts("explanation")
        if item.mode is ExplanationMode.CHECK_ONLY
        and item.grading_result_hash == grade.result_hash
    )
    solution = next(
        item
        for item in service.store.artifacts("explanation")
        if item.mode is ExplanationMode.SOLUTION_AFTER_ATTEMPT
        and item.session_id == session_id
    )
    cases = []

    def rejected(action) -> None:
        try:
            action()
        except (KeyError, TypeError, ValueError):
            cases.append(True)
        else:
            cases.append(False)

    forged_presented = _rehash(
        presented,
        "presentation_hash",
        question_text="forged checksum-valid question",
    )
    rejected(
        lambda: verify_presented_exercise_binding(
            forged_presented, instance, spec, session_id=session_id
        )
    )
    forged_receipt = _rehash(
        receipt, "receipt_hash", compiler_identity="forged-compiler"
    )
    rejected(
        lambda: verify_compilation_receipt(
            forged_receipt,
            service.chemistry,
            graph_hash=graph.graph_hash,
            graph=graph,
            spec=spec,
        )
    )
    forged_grade = _rehash(
        grade,
        "result_hash",
        correctness_status=GradingStatus.CORRECT,
        score="1",
        correct_nodes=(graph.root_result_node_id,),
        incorrect_nodes=(),
        first_incorrect_node=None,
        error_diagnoses=(),
    )
    expected_grade = grade_answer(
        instance,
        answer,
        graph,
        attempt_id=grade.attempt_id,
        created_at=grade.created_at,
    )
    rejected(lambda: _require_equal(forged_grade, expected_grade, "forged grading"))
    forged_plan = _rehash(
        plan,
        "plan_hash",
        grading_result_hash=None,
        diagnosis_hashes=(),
    )
    rejected(
        lambda: render_hint(
            forged_plan,
            graph,
            hint.level,
            language=hint.language,
            grading=grade,
        )
    )
    forged_hint = _rehash(hint, "hint_hash", text=hint.text + " forged")
    rejected(
        lambda: _require_equal(
            forged_hint,
            render_hint(
                plan,
                graph,
                hint.level,
                language=hint.language,
                grading=grade,
            ),
            "forged hint",
        )
    )
    forged_check = _rehash(check, "explanation_hash", text=check.text + " forged")
    rejected(lambda: verify_explanation(forged_check, graph, grading=grade))
    full = render_explanation(graph, language="en", mode=ExplanationMode.FULL)
    forged_full = _rehash(full, "explanation_hash", text=full.text + " forged")
    rejected(lambda: verify_explanation(forged_full, graph))
    forged_solution = _rehash(solution, "explanation_hash", session_state_hash="0" * 64)
    rejected(
        lambda: verify_explanation(
            forged_solution,
            graph,
            session_id=session_id,
            session_state_hash=solution.session_state_hash,
        )
    )
    events = service.store.events(session_id)
    state, _ = start_session(
        instance, session_id=session_id, created_at=events[0].created_at
    )
    for event in events[1:]:
        state = apply_event(state, event)
    forged_session = _rehash(state, "session_hash", status="ABANDONED")
    rejected(lambda: _require_equal(forged_session, stored, "forged session"))
    forged_event = _rehash(
        events[-1],
        "event_hash",
        payload={"explanation_hash": "0" * 64},
    )
    rejected(lambda: service.store._verify_event_artifacts(stored, forged_event))
    EducationalArtifactAuthorityVerifier(service).verify()
    return {
        "tamper_cases": len(cases),
        "accepted_semantic_tampers": sum(not item for item in cases),
        "categories": (
            "PresentedExercise",
            "CompilationReceipt",
            "GradingResult",
            "HintPlan",
            "HintArtifact",
            "CHECK_ONLY",
            "FullExplanation",
            "SolutionSessionBinding",
            "TutorSession",
            "TutorEvent",
        ),
        "structural_status": service.store.verify()["status"],
        "authority_status": "AUTHORITY_VERIFIED",
    }


def _public_boundary(catalog) -> dict:
    leaks = 0
    forbidden = (
        "graph_hash",
        "receipt",
        "hidden_expected_answer",
        "counterfactual",
        "split_",
        "event_hash",
        "provenance",
    )
    for index in range(1_000):
        entry = catalog.entries[index % len(catalog.entries)]
        instance = instantiate_variant(
            entry.internal_instance,
            entry.exercise_spec,
            entry.graph,
            seed=index,
            language=("ru", "en")[index % 2],
        )
        presented = present_exercise(
            instance, entry.exercise_spec, session_id=f"public-{index}"
        )
        value = public_exercise(presented, session_status="PRESENTED")
        encoded = json.dumps(asdict(value), ensure_ascii=False, sort_keys=True)
        if any(token in encoded for token in forbidden):
            leaks += 1
        if entry.graph.graph_hash in encoded or receipt_value(entry) in encoded:
            leaks += 1
    return {"probe_count": 1_000, "leaks": leaks}


def _split_summary(catalog) -> dict:
    invalid = 0
    rows = {}
    semantic = {entry.semantic_key.semantic_key_hash for entry in catalog.entries}
    for manifest in catalog.split_manifests:
        development = set(manifest["development"])
        final = set(manifest["final_validation"])
        intersection = len(development & final)
        if (
            intersection != manifest["intersection_count"]
            or development | final != semantic
            or not development
            or not final
        ):
            invalid += 1
        rows[manifest["axis"]] = {
            "axis_kind": manifest["axis_kind"],
            "development": len(development),
            "final_validation": len(final),
            "intersection": intersection,
            "universe_count": manifest["universe_count"],
        }
    return {"manifest_count": len(rows), "invalid_manifests": invalid, "axes": rows}


def _store_state(service, session_id: str):
    with sqlite3.connect(service.store.database_path) as connection:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("artifacts", "events", "sessions")
        )
    return counts, service.store.get_session(session_id).session_hash


def _rehash(value, hash_field: str, **changes):
    provisional = replace(value, **changes, **{hash_field: ""})
    body = asdict(provisional)
    body.pop(hash_field)
    return replace(provisional, **{hash_field: content_hash(body)})


def _require_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise ValueError(label)


def receipt_value(entry) -> str:
    return entry.compilation_receipt.receipt_hash
