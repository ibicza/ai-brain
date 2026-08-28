"""CPU latency and memory benchmark for trusted educational operations."""

from __future__ import annotations

import statistics
import time
import tracemalloc
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.exercise_generation import (
    derive_exercise_variant,
    generate_exercise,
)
from ai_brain.stage2.education.explanations import render_explanation
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import (
    ExerciseFamily,
    ExplanationMode,
    HintLevel,
    StudentAnswerKind,
)
from ai_brain.stage2.education.sessions import apply_event, make_event, start_session
from ai_brain.stage2.facts.canonical import content_hash


def run_m29_benchmark(
    adapter: ChemistryEducationAdapter, *, interaction_count: int = 10_000
) -> dict[str, Any]:
    if interaction_count < 100:
        raise ValueError("educational benchmark requires at least 100 interactions")
    pool = tuple(
        generate_exercise(
            adapter,
            tuple(ExerciseFamily)[index % len(ExerciseFamily)],
            seed=50_000 + index,
            language=("ru", "en")[index % 2],
        )
        for index in range(24)
    )
    symbols = set(adapter.service.manifest["supported_elements"])
    samples: dict[str, list[int]] = defaultdict(list)
    started = time.perf_counter_ns()
    tracemalloc.start()
    for index in range(interaction_count):
        spec, instance, graph = pool[index % len(pool)]
        operation = index % 10
        if operation == 0:
            _measure(
                samples,
                "graph_verification",
                lambda graph=graph: verify_derivation_graph(graph),
            )
        elif operation == 1:
            _measure(
                samples,
                "concise_render",
                lambda graph=graph, language=instance.language: render_explanation(
                    graph, language=language, mode=ExplanationMode.CONCISE
                ),
            )
        elif operation == 2:
            _measure(
                samples,
                "full_render",
                lambda graph=graph, language=instance.language: render_explanation(
                    graph, language=language, mode=ExplanationMode.FULL
                ),
            )
        elif operation == 3:
            _measure(
                samples,
                "exercise_generation",
                lambda instance=instance, spec=spec, graph=graph, seed=2_000_000 + index: (
                    derive_exercise_variant(instance, spec, graph, seed=seed)
                ),
            )
        elif operation == 4:
            raw = _answer_text(
                spec.accepted_answer_type, instance.hidden_expected_answer
            )
            _measure(
                samples,
                "answer_parsing",
                lambda raw=raw, kind=spec.accepted_answer_type: parse_student_answer(
                    raw,
                    kind,
                    supported_symbols=symbols,
                    confirmed=True,
                ),
            )
        elif operation in {5, 6}:
            raw = (
                _counterfactual_text(instance)
                if operation == 6
                else _answer_text(
                    spec.accepted_answer_type, instance.hidden_expected_answer
                )
            )
            answer = parse_student_answer(
                raw,
                spec.accepted_answer_type,
                supported_symbols=symbols,
                confirmed=True,
            )
            label = "grading" if operation == 5 else "counterfactual_diagnosis"
            _measure(
                samples,
                label,
                lambda instance=instance, answer=answer, graph=graph, attempt_id=f"benchmark-{index}": (
                    grade_answer(
                        instance,
                        answer,
                        graph,
                        attempt_id=attempt_id,
                        created_at="2026-08-28T00:00:00Z",
                    )
                ),
            )
        elif operation == 7:
            plan = build_hint_plan(instance.instance_id, graph)
            _measure(
                samples,
                "hint_generation",
                lambda plan=plan, graph=graph, language=instance.language: render_hint(
                    plan, graph, HintLevel.NEXT_STEP, language=language
                ),
            )
        elif operation == 8:
            _measure(
                samples,
                "session_transition",
                lambda instance=instance, index=index: _session_transition(
                    instance, index
                ),
            )
        else:
            _measure(
                samples,
                "educational_replay",
                lambda graph=graph, instance=instance: (
                    verify_derivation_graph(graph),
                    content_hash(instance),
                ),
            )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed_ns = time.perf_counter_ns() - started
    metrics = {key: _latency(values) for key, values in sorted(samples.items())}
    return {
        "status": "PASS",
        "device": "CPU-only deterministic trusted path",
        "interaction_count": interaction_count,
        "elapsed_seconds": f"{elapsed_ns / 1_000_000_000:.6f}",
        "throughput_per_second": f"{interaction_count / (elapsed_ns / 1_000_000_000):.3f}",
        "peak_python_memory_bytes": peak,
        "operations": metrics,
        "benchmark_hash": content_hash(
            {
                "interaction_count": interaction_count,
                "metrics": metrics,
                "peak_python_memory_bytes": peak,
            }
        ),
    }


def _measure(
    samples: dict[str, list[int]], label: str, operation: Callable[[], Any]
) -> None:
    started = time.perf_counter_ns()
    operation()
    samples[label].append(time.perf_counter_ns() - started)


def _latency(values: list[int]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p50_ms": f"{statistics.median(ordered) / 1_000_000:.6f}",
        "p95_ms": f"{_percentile(ordered, 0.95) / 1_000_000:.6f}",
        "p99_ms": f"{_percentile(ordered, 0.99) / 1_000_000:.6f}",
    }


def _percentile(ordered: list[int], fraction: float) -> int:
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def _session_transition(instance, index):
    session, _ = start_session(
        instance,
        session_id=f"benchmark-session-{index}",
        created_at="2026-08-28T00:00:00Z",
    )
    event = make_event(
        session.session_id,
        sequence=2,
        event_type="HINT_ISSUED",
        payload={"hint_hash": "0" * 64, "level": 1},
        previous_event_hash=session.last_event_hash,
        created_at="2026-08-28T00:00:01Z",
    )
    return apply_event(session, event)


def _answer_text(kind, expected):
    if kind == StudentAnswerKind.NUMERIC_WITH_UNIT:
        return f"{expected['value']} {expected['unit']}"
    if kind == StudentAnswerKind.ELEMENT_COUNT_MAP:
        return ",".join(
            f"{key}:{value}" for key, value in expected["element_counts"].items()
        )
    if kind == StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL:
        return f"[{expected['lower']}, {expected['upper']}]"
    return expected["text"]


def _counterfactual_text(instance):
    candidate = next(
        (
            item
            for item in instance.counterfactuals
            if {"value", "unit"} <= item.answer.keys()
        ),
        None,
    )
    if candidate is not None:
        return f"{candidate.answer['value']} {candidate.answer['unit']}"
    return (
        _answer_text(
            StudentAnswerKind.NUMERIC_WITH_UNIT,
            instance.hidden_expected_answer,
        )
        if {"value", "unit"} <= instance.hidden_expected_answer.keys()
        else "invalid"
    )
