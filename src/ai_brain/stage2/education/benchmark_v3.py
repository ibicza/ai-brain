"""Separated M-29.2 runtime/currentness and full-verification timings."""

from __future__ import annotations

from time import perf_counter

from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.currentness import (
    evaluate_dependency_currentness,
    evaluate_entry_currentness,
    require_current,
)
from ai_brain.stage2.education.exercise_generation import (
    instantiate_variant,
    present_exercise,
)
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import ExerciseFamily, HintLevel


def run_m292_stage_benchmark(service, *, samples: int = 1_000) -> dict:
    if samples < 100:
        raise ValueError("M-29.2 stage benchmark requires at least 100 samples")
    entry = next(
        item
        for item in service.catalog.entries
        if item.exercise_spec.family == ExerciseFamily.MOLAR_MASS_SIMPLE
    )
    instance = entry.internal_instance
    expected = instance.hidden_expected_answer
    correct = parse_student_answer(
        f"{expected['value']} {expected['unit']}",
        entry.exercise_spec.accepted_answer_type,
        supported_symbols=set(service.chemistry.manifest["supported_elements"]),
        confirmed=True,
    )
    wrong = parse_student_answer(
        f"0 {expected['unit']}",
        entry.exercise_spec.accepted_answer_type,
        supported_symbols=set(service.chemistry.manifest["supported_elements"]),
        confirmed=True,
    )
    grading = grade_answer(
        instance,
        wrong,
        entry.graph,
        attempt_id="m292-benchmark-targeted",
        created_at="2026-08-28T04:00:00Z",
    )
    replay_id = "m292-benchmark-replay"
    try:
        service.store.get_session(replay_id)
    except KeyError:
        service.create_exercise(
            entry.exercise_spec.family,
            seed=2_925,
            language="en",
            session_id=replay_id,
            created_at="2026-08-28T04:00:00Z",
        )
    receipt = service.store.get_artifact(
        service.store.get_artifact(
            service.store.get_session(replay_id).exercise_hash,
            expected_kind="exercise_instance_internal",
        ).compilation_receipt_hash,
        expected_kind="compilation_receipt",
    )

    def current_session_closure():
        stored = service.store.get_session(replay_id)
        stored_instance = service.store.get_artifact(
            stored.exercise_hash, expected_kind="exercise_instance_internal"
        )
        spec = service.store.get_artifact(
            stored_instance.exercise_spec_hash, expected_kind="exercise_spec"
        )
        graph = service.store.get_artifact(
            stored.graph_hash, expected_kind="derivation_graph"
        )
        require_current(
            evaluate_dependency_currentness(
                service.chemistry, graph, receipt, stored_instance, spec
            )
        )

    operations = {
        "presentation": lambda index: (
            require_current(evaluate_entry_currentness(service.chemistry, entry)),
            present_exercise(
                instantiate_variant(
                    instance,
                    entry.exercise_spec,
                    entry.graph,
                    seed=index,
                    language=("ru", "en")[index % 2],
                ),
                entry.exercise_spec,
                session_id=f"benchmark-{index}",
            ),
        ),
        "grading": lambda index: (
            current_session_closure(),
            grade_answer(
                instance,
                correct,
                entry.graph,
                attempt_id=f"m292-benchmark-grade-{index}",
                created_at="2026-08-28T04:00:00Z",
            ),
        ),
        "generic_hint": lambda index: (
            current_session_closure(),
            render_hint(
                build_hint_plan(instance.instance_id, entry.graph),
                entry.graph,
                HintLevel.ORIENT,
                language=("ru", "en")[index % 2],
            ),
        ),
        "targeted_hint": lambda index: (
            current_session_closure(),
            render_hint(
                build_hint_plan(instance.instance_id, entry.graph, grading=grading),
                entry.graph,
                HintLevel.ORIENT,
                language=("ru", "en")[index % 2],
                grading=grading,
            ),
        ),
    }
    results = {}
    before = service.execution_monitor.count
    for name, operation in operations.items():
        started = perf_counter()
        for index in range(samples):
            operation(index)
        elapsed = perf_counter() - started
        results[name] = _metric(samples, elapsed)
    replay_samples = max(10, samples // 100)
    started = perf_counter()
    for _ in range(replay_samples):
        result = service._replay_internal(replay_id)
        if result["status"] != "CURRENT":
            raise ValueError("benchmark replay is not current")
    results["replay_currentness"] = _metric(replay_samples, perf_counter() - started)
    started = perf_counter()
    verification = service.verify()
    results["full_service_verify"] = _metric(1, perf_counter() - started)
    return {
        "status": "PASS",
        "samples_per_hot_stage": samples,
        "stages": results,
        "runtime_chemistry_executions": service.execution_monitor.count - before,
        "full_verify_status": verification["status"],
        "offline_catalog_compilation_included": False,
    }


def _metric(count: int, elapsed: float) -> dict[str, float | int]:
    return {
        "count": count,
        "elapsed_seconds": elapsed,
        "operations_per_second": count / elapsed,
        "mean_milliseconds": elapsed * 1_000 / count,
    }
