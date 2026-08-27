"""CPU performance measurements for the bounded chemistry domain."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import molar_mass
from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    build_knowledge_snapshot,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService


def run_benchmark(
    service: ChemistryDomainService, *, calculation_count: int = 10_000
) -> dict[str, Any]:
    parser = FormulaParser(set(service.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(service.memory, service.manifest)
    formulas = ("H2O", "CO2", "NaCl", "CaCO3", "H2SO4", "Al2(SO4)3", "C6H12O6")
    parse_samples = _measure(
        lambda index: parser.parse(formulas[index % len(formulas)]), 1000
    )
    calculation_samples = _measure(
        lambda index: molar_mass(parser, snapshot, formulas[index % len(formulas)]),
        calculation_count,
    )
    route_samples = _measure(
        lambda index: service.route_text(
            f"Calculate the molar mass of {formulas[index % len(formulas)]}.", "en"
        ),
        200,
    )
    return {
        "device": "CPU",
        "calculation_count": calculation_count,
        "formula_parse_ms": _stats(parse_samples),
        "molar_mass_ms": _stats(calculation_samples),
        "controlled_route_ms": _stats(route_samples),
        "calculations_per_second": calculation_count
        / (sum(calculation_samples) / 1000),
    }


def write_benchmark(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _measure(operation: Callable[[int], Any], count: int) -> list[float]:
    samples = []
    for index in range(count):
        started = time.perf_counter_ns()
        operation(index)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return samples


def _stats(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50": statistics.median(ordered),
        "p95": ordered[int(len(ordered) * 0.95) - 1],
        "p99": ordered[int(len(ordered) * 0.99) - 1],
    }
