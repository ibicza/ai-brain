"""CPU benchmark separating runtime interaction from offline compilation."""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter

from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.exercise_generation import (
    instantiate_variant,
    present_exercise,
)
from ai_brain.stage2.education.explanations import (
    build_explanation_plan,
    render_explanation,
)
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import ExplanationMode, HintLevel
from ai_brain.stage2.education.sessions import apply_event, make_event, start_session


def run_m291_runtime_benchmark(service, *, interaction_count: int = 10_000) -> dict:
    if interaction_count < 10_000:
        raise ValueError("M-29.1 runtime benchmark requires 10,000 interactions")
    entries = service.catalog.entries
    numeric_entries = [
        entry
        for entry in entries
        if {"value", "unit"} <= entry.internal_instance.hidden_expected_answer.keys()
    ]
    sample = numeric_entries[0]
    expected = sample.internal_instance.hidden_expected_answer
    correct_answer = parse_student_answer(
        f"{expected['value']} {expected['unit']}",
        sample.exercise_spec.accepted_answer_type,
        supported_symbols=set(service.chemistry.manifest["supported_elements"]),
        confirmed=True,
    )
    wrong_answer = parse_student_answer(
        f"0 {expected['unit']}",
        sample.exercise_spec.accepted_answer_type,
        supported_symbols=set(service.chemistry.manifest["supported_elements"]),
        confirmed=True,
    )
    wrong_grade = grade_answer(
        sample.internal_instance,
        wrong_answer,
        sample.graph,
        attempt_id="benchmark.wrong-diagnosis",
        created_at="2026-08-28T00:00:00Z",
    )
    transition_session, _ = start_session(
        sample.internal_instance,
        session_id="m291-benchmark-transition",
        created_at="2026-08-28T00:00:00Z",
    )
    transition_event = make_event(
        transition_session.session_id,
        sequence=2,
        event_type="ANSWER_SUBMITTED",
        payload={"student_answer_hash": correct_answer.answer_hash},
        previous_event_hash=transition_session.last_event_hash,
        created_at="2026-08-28T00:00:01Z",
    )
    replay_session_id = "m291-authority-presentation"
    try:
        service.store.get_session(replay_session_id)
    except KeyError:
        service.create_exercise(
            sample.exercise_spec.family,
            seed=291,
            language="en",
            session_id=replay_session_id,
            created_at="2026-08-28T00:00:00Z",
        )
    before = service.execution_monitor.count
    started = perf_counter()
    stage_totals = {
        "presented_exercise": 0.0,
        "graph_verification": 0.0,
        "explanation_plan": 0.0,
        "trusted_text_regeneration": 0.0,
        "student_answer_parsing": 0.0,
        "grading": 0.0,
        "independent_diagnosis": 0.0,
        "hint_generation": 0.0,
        "semantic_store_verification": 0.0,
        "live_educational_replay": 0.0,
        "session_transition": 0.0,
    }
    stage_counts = {key: 0 for key in stage_totals}
    frequent_stages = (0, 1, 2, 3, 4, 5, 6, 7, 10)
    for index in range(interaction_count):
        entry = entries[index % len(entries)]
        bucket = index % 100
        if bucket == 98:
            stage = 8
        elif bucket == 99:
            stage = 9
        else:
            stage = frequent_stages[bucket % len(frequent_stages)]
        mark = perf_counter()
        if stage == 0:
            instance = instantiate_variant(
                entry.internal_instance,
                entry.exercise_spec,
                entry.graph,
                seed=index,
                language=("ru", "en")[index % 2],
            )
            asdict(
                present_exercise(instance, entry.exercise_spec, session_id=f"b{index}")
            )
            key = "presented_exercise"
        elif stage == 1:
            verify_derivation_graph(entry.graph)
            key = "graph_verification"
        elif stage == 2:
            build_explanation_plan(
                entry.graph,
                language=("ru", "en")[index % 2],
                mode=ExplanationMode.CONCISE,
            )
            key = "explanation_plan"
        elif stage == 3:
            render_explanation(
                entry.graph,
                language=("ru", "en")[index % 2],
                mode=ExplanationMode.CONCISE,
            )
            key = "trusted_text_regeneration"
        elif stage == 4:
            numeric = numeric_entries[index % len(numeric_entries)]
            numeric_expected = numeric.internal_instance.hidden_expected_answer
            parse_student_answer(
                f"{numeric_expected['value']} {numeric_expected['unit']}",
                numeric.exercise_spec.accepted_answer_type,
                supported_symbols=set(service.chemistry.manifest["supported_elements"]),
                confirmed=True,
            )
            key = "student_answer_parsing"
        elif stage == 5:
            grade_answer(
                sample.internal_instance,
                correct_answer,
                sample.graph,
                attempt_id=f"benchmark.grade.{index}",
                created_at="2026-08-28T00:00:00Z",
            )
            key = "grading"
        elif stage == 6:
            grade_answer(
                sample.internal_instance,
                wrong_answer,
                sample.graph,
                attempt_id=f"benchmark.diagnosis.{index}",
                created_at="2026-08-28T00:00:00Z",
            )
            key = "independent_diagnosis"
        elif stage == 7:
            plan = build_hint_plan(
                sample.internal_instance.instance_id,
                sample.graph,
                grading=wrong_grade,
            )
            render_hint(
                plan,
                sample.graph,
                HintLevel.ORIENT,
                language=("ru", "en")[index % 2],
                grading=wrong_grade,
            )
            key = "hint_generation"
        elif stage == 8:
            service.store.verify()
            key = "semantic_store_verification"
        elif stage == 9:
            service._replay_internal(replay_session_id)
            key = "live_educational_replay"
        else:
            apply_event(transition_session, transition_event)
            key = "session_transition"
        stage_totals[key] += perf_counter() - mark
        stage_counts[key] += 1
    elapsed = perf_counter() - started
    runtime_executions = service.execution_monitor.count - before
    return {
        "interaction_count": interaction_count,
        "elapsed_seconds": elapsed,
        "interactions_per_second": interaction_count / elapsed,
        "stage_seconds": stage_totals,
        "stage_counts": stage_counts,
        "runtime_chemistry_executions": runtime_executions,
        "offline_compilation_included": False,
    }
