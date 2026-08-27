"""M-28.2 provenance-aware CPU benchmark."""

from __future__ import annotations

import json
import statistics
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.benchmark_v2 import run_m281_benchmark
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    ATOMIC_WEIGHTS,
    build_knowledge_snapshot,
)
from ai_brain.stage2.domains.chemistry.provenance import resolve_source_derivation
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_derivation import verify_source_chain


def run_m282_benchmark(
    service: ChemistryDomainService, *, calculation_count: int = 10_000
) -> dict[str, Any]:
    chain = service.manifest["source_chain"]
    source = service.memory.get_source_record("derived_ciaaw_atomic_weights_2024")
    bindings = tuple(service.manifest["source_record_bindings"])
    tracemalloc.start()
    matrix = {
        "source_chain_v3_verification": _measure(
            lambda _: verify_source_chain(service.root / "sources"), 10
        ),
        "derivation_resolution": _measure(
            lambda _: resolve_source_derivation(
                source,
                chain,
                service.memory,
                source_record_bindings=bindings,
            ),
            100,
        ),
        "upstream_state_resolution": _measure(
            lambda _: tuple(
                service.memory.get_source_state(source_id)
                for source_id in (
                    "official_ciaaw_standard_weights_2024",
                    "official_ciaaw_abridged_weights_2024",
                )
            ),
            1000,
        ),
        "knowledge_snapshot_v3": _measure(
            lambda _: build_knowledge_snapshot(
                service.memory,
                service.manifest,
                ("H", "O"),
                requirements=(ATOMIC_WEIGHTS,),
            ),
            25,
        ),
        "tool_proposal_creation": _measure(
            lambda _: service.prepare_tool(
                "chemistry_molar_mass",
                {
                    "formula": "H2O",
                    "mode": "CONVENTIONAL_CLASSROOM",
                    "unit": "g/mol",
                    "significant_digits": 6,
                },
            ),
            100,
        ),
    }
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    prior = run_m281_benchmark(service, calculation_count=calculation_count)
    return {
        "status": "PASS",
        "device": "CPU",
        "provenance_matrix_ms": matrix,
        "mixed_calculations": prior,
        "peak_python_memory_bytes": max(peak, prior["peak_python_memory_bytes"]),
    }


def write_m282_benchmark(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _measure(operation: Callable[[int], Any], count: int) -> dict[str, float]:
    samples = []
    started = time.perf_counter()
    for index in range(count):
        item_started = time.perf_counter_ns()
        operation(index)
        samples.append((time.perf_counter_ns() - item_started) / 1_000_000)
    elapsed = time.perf_counter() - started
    ordered = sorted(samples)
    return {
        "count": float(count),
        "p50_ms": statistics.median(ordered),
        "p95_ms": _percentile(ordered, 0.95),
        "p99_ms": _percentile(ordered, 0.99),
        "throughput_per_second": count / elapsed,
    }


def _percentile(values: list[float], fraction: float) -> float:
    return values[min(len(values) - 1, int(len(values) * fraction))]
