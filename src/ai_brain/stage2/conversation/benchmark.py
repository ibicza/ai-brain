"""CPU-only benchmark helpers for bounded conversation hot paths."""

from __future__ import annotations

import statistics
import tracemalloc
from collections.abc import Callable
from time import perf_counter
from typing import Any

from ai_brain.stage2.conversation.intents import parse_intent
from ai_brain.stage2.conversation.models import ConversationState
from ai_brain.stage2.conversation.pending_actions import (
    authorize_pending,
    prepare_pending_action,
)
from ai_brain.stage2.conversation.state_machine import require_transition


def measure_operations(
    count: int, operation: Callable[[int], Any]
) -> dict[str, object]:
    """Measure an exact operation count with latency quantiles and Python peak memory."""
    if count < 1:
        raise ValueError("benchmark count must be positive")
    timings: list[float] = []
    tracemalloc.start()
    started = perf_counter()
    for index in range(count):
        before = perf_counter()
        operation(index)
        timings.append((perf_counter() - before) * 1_000)
    elapsed = perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timings.sort()
    return {
        "count": count,
        "p50_ms": f"{statistics.median(timings):.6f}",
        "p95_ms": f"{timings[max(0, int(count * 0.95) - 1)]:.6f}",
        "p99_ms": f"{timings[max(0, int(count * 0.99) - 1)]:.6f}",
        "throughput_per_second": f"{count / elapsed:.3f}",
        "peak_python_bytes": peak,
    }


def benchmark_turn_parsing(count: int = 10_000) -> dict[str, object]:
    if count < 10_000:
        raise ValueError("M-30 benchmark requires 10,000 turns")
    turns = (
        ("Начать занятие", "ru"),
        ("Give me an exercise", "en"),
        ("Дай подсказку", "ru"),
        ("Show my progress", "en"),
        ("Пауза", "ru"),
        ("Resume the session", "en"),
        ("Покажи решение", "ru"),
        ("End the lesson", "en"),
    )
    return measure_operations(
        count, lambda index: parse_intent(*turns[index % len(turns)])
    )


def benchmark_state_transition(count: int = 10_000) -> dict[str, object]:
    if count < 10_000:
        raise ValueError("M-30 benchmark requires 10,000 state transitions")
    transitions = (
        (ConversationState.IDLE, ConversationState.EXERCISE_ACTIVE),
        (ConversationState.EXERCISE_ACTIVE, ConversationState.AWAITING_CLARIFICATION),
        (ConversationState.AWAITING_CLARIFICATION, ConversationState.EXERCISE_ACTIVE),
        (ConversationState.EXERCISE_ACTIVE, ConversationState.PAUSED),
        (ConversationState.PAUSED, ConversationState.EXERCISE_ACTIVE),
        (ConversationState.EXERCISE_ACTIVE, ConversationState.CLOSED),
    )
    return measure_operations(
        count,
        lambda index: require_transition(*transitions[index % len(transitions)]),
    )


def benchmark_pending_actions(count: int = 10_000) -> dict[str, dict[str, object]]:
    if count < 10_000:
        raise ValueError("M-30 benchmark requires 10,000 pending actions")

    def prepare(index: int):
        return prepare_pending_action(
            learner_id="benchmark-learner",
            conversation_id="benchmark-conversation",
            action_kind="EXPLAIN_MOLAR_MASS",
            request_hash=f"request-{index}",
            language="en",
            payload={"formula": "H2O"},
            dependency_snapshot=("catalog", "facts", "sources", "tool"),
            previous_state=ConversationState.IDLE,
            created_at="2026-01-01T00:00:00Z",
        )

    preparation = measure_operations(count, prepare)
    prepared = tuple(prepare(index) for index in range(count))
    confirmation = measure_operations(
        count,
        lambda index: authorize_pending(
            prepared[index],
            learner_id="benchmark-learner",
            conversation_id="benchmark-conversation",
            language="en",
            dependency_snapshot=("catalog", "facts", "sources", "tool"),
            now="2026-01-01T00:00:01Z",
        ),
    )
    return {
        "pending_action_preparation": preparation,
        "pending_confirmation": confirmation,
    }
