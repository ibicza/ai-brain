"""Separate SQL, full FactMemory, and unified-response latency measurement."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.router import (
    ExactUnifiedRouter,
    ToolRegistry,
    UnifiedRouterService,
    create_request,
)
from ai_brain.stage2.router.models import RequestSourceKind


def benchmark_fact_response(
    fact_root: Path,
    *,
    subject: str,
    predicate_id: str,
    samples: int = 200,
) -> dict[str, Any]:
    if samples < 10:
        raise ValueError("at least ten samples are required")
    memory = FactMemory.open(fact_root)
    service = UnifiedRouterService(
        ExactUnifiedRouter(tool_registry=ToolRegistry.default(), fact_memory=memory)
    )

    def sql_lookup() -> None:
        with memory.database.connect() as connection:
            connection.execute(
                "SELECT claim_id FROM claims WHERE subject_entity_id = ? AND predicate_id = ? ORDER BY recorded_at, claim_id",
                (subject, predicate_id),
            ).fetchall()

    def full_query() -> None:
        query = memory.make_query(subject=subject, predicate_id=predicate_id)
        memory.query(query)

    def unified() -> None:
        request = create_request(
            RequestSourceKind.STRUCTURED_FACT,
            structured_payload={"subject": subject, "predicate_id": predicate_id},
        )
        service.handle(request)

    return {
        "samples": samples,
        "INDEXED_SQL_LOOKUP": _measure(sql_lookup, samples),
        "END_TO_END_FACT_QUERY": _measure(full_query, samples),
        "UNIFIED_ROUTER_FACT_RESPONSE": _measure(unified, samples),
    }


def _measure(operation: Callable[[], None], samples: int) -> dict[str, float]:
    values = []
    for _ in range(samples):
        started = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(values)
    return {
        "p50_ms": _percentile(ordered, 0.50),
        "p95_ms": _percentile(ordered, 0.95),
        "p99_ms": _percentile(ordered, 0.99),
    }


def _percentile(values: list[float], quantile: float) -> float:
    index = max(0, math.ceil(len(values) * quantile) - 1)
    return values[index]
