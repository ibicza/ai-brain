"""Mixed CPU performance matrix for M-28.1 chemistry operations."""

from __future__ import annotations

import json
import statistics
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import (
    entity_amount,
    mass_amount,
    molar_mass,
    render_significant,
)
from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    atomic_weight_answer,
    build_knowledge_snapshot,
)
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.domains.chemistry.resolver import resolve_chemistry_element
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_derivation import verify_source_chain
from ai_brain.stage2.facts.persistence import FactDatabase


def run_m281_benchmark(
    service: ChemistryDomainService, *, calculation_count: int = 10_000
) -> dict[str, Any]:
    parser = FormulaParser(set(service.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(service.memory, service.manifest)
    formulas = ("H2O", "CO2", "NaCl", "CaCO3", "H2SO4", "Al2(SO4)3", "C6H12O6")
    tracemalloc.start()
    started = time.perf_counter_ns()
    mixed_samples = []
    for index in range(calculation_count):
        formula = formulas[index % len(formulas)]
        operation_started = time.perf_counter_ns()
        mode = index % 6
        if mode == 0:
            parser.parse(formula)
        elif mode == 1:
            molar_mass(parser, snapshot, formula)
        elif mode == 2:
            molar_mass(parser, snapshot, formula, mode="NATURAL_VARIABILITY_ENVELOPE")
        elif mode == 3:
            mass_amount(parser, snapshot, formula, str(index % 100 + 1), "g", "mol")
        elif mode == 4:
            entity_amount(
                parser,
                snapshot,
                str(index % 100 + 1),
                "mol",
                "entities",
                "FORMULA_ENTITIES",
                formula=formula,
            )
        else:
            entity_amount(
                parser,
                snapshot,
                str(index % 100 + 1),
                "mol",
                "entities",
                "TOTAL_ATOMS_IN_FORMULA",
                formula=formula,
            )
        mixed_samples.append((time.perf_counter_ns() - operation_started) / 1_000_000)
    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    _, prepared, proposal = service.prepare_tool(
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    result, _ = service.confirm_and_execute(
        prepared, proposal, identity="m281-benchmark"
    )
    assert result is not None
    matrix: dict[str, dict[str, float]] = {}
    matrix["source_chain_verification"] = _measure(
        lambda _: verify_source_chain(service.root / "sources"), 5
    )
    matrix["domain_pack_load"] = _measure(
        lambda _: ChemistryDomainService.open(service.root), 5
    )
    matrix["exact_element_resolution"] = _measure(
        lambda index: resolve_chemistry_element(
            service.memory, ("H", "C", "Fe")[index % 3], "en"
        ),
        500,
    )
    matrix["atomic_weight_answer"] = _measure(
        lambda index: atomic_weight_answer(
            service.memory,
            service.manifest,
            ("H", "C", "Fe")[index % 3],
        ),
        10,
    )
    matrix["formula_parse"] = _measure(
        lambda index: parser.parse(formulas[index % len(formulas)]), 1000
    )
    matrix["knowledge_snapshot"] = _measure(
        lambda _: build_knowledge_snapshot(
            service.memory, service.manifest, ("H", "O")
        ),
        5,
    )
    matrix["conventional_molar_mass"] = _measure(
        lambda index: molar_mass(parser, snapshot, formulas[index % len(formulas)]),
        1000,
    )
    matrix["envelope_molar_mass"] = _measure(
        lambda index: molar_mass(
            parser,
            snapshot,
            formulas[index % len(formulas)],
            mode="NATURAL_VARIABILITY_ENVELOPE",
        ),
        1000,
    )
    matrix["mass_amount"] = _measure(
        lambda index: mass_amount(
            parser, snapshot, formulas[index % len(formulas)], "10", "g", "mol"
        ),
        1000,
    )
    matrix["formula_entities"] = _measure(
        lambda index: entity_amount(
            parser,
            snapshot,
            "0.5",
            "mol",
            "entities",
            "FORMULA_ENTITIES",
            formula=formulas[index % len(formulas)],
        ),
        1000,
    )
    matrix["total_atoms"] = _measure(
        lambda index: entity_amount(
            parser,
            snapshot,
            "0.5",
            "mol",
            "entities",
            "TOTAL_ATOMS_IN_FORMULA",
            formula=formulas[index % len(formulas)],
        ),
        1000,
    )
    matrix["significant_rendering"] = _measure(
        lambda index: render_significant(Decimal(index + 1) / Decimal(7)), 1000
    )
    matrix["controlled_route"] = _measure(
        lambda index: service.route_text(
            f"Calculate the molar mass of {formulas[index % len(formulas)]}.", "en"
        ),
        100,
    )
    matrix["confirmed_response"] = _measure(
        lambda index: _confirmed_response(service, formulas[index % len(formulas)]),
        5,
    )
    matrix["replay"] = _measure(
        lambda _: replay_chemistry_result(
            result.output, service.memory, service.manifest
        ),
        100,
    )
    matrix["fact_memory_verify"] = _measure(lambda _: service.memory.verify(), 3)
    with tempfile.TemporaryDirectory(prefix="m281-benchmark-") as directory:
        backup_path = Path(directory) / "baseline-backup"
        service.memory.database.backup(backup_path)
        matrix["backup"] = _measure(
            lambda index: service.memory.database.backup(
                Path(directory) / f"backup-{index}"
            ),
            3,
        )
        matrix["restore"] = _measure(
            lambda index: FactDatabase.restore(
                backup_path, Path(directory) / f"restore-{index}"
            ),
            3,
        )
    return {
        "device": "CPU",
        "calculation_count": calculation_count,
        "mixed_calculation_ms": _stats(mixed_samples),
        "calculations_per_second": calculation_count / elapsed_seconds,
        "peak_python_memory_bytes": peak,
        "performance_matrix_ms": matrix,
    }


def write_m281_benchmark(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _measure(operation: Callable[[int], Any], count: int) -> dict[str, float]:
    samples = []
    for index in range(count):
        started = time.perf_counter_ns()
        operation(index)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return _stats(samples)


def _confirmed_response(service: ChemistryDomainService, formula: str) -> Any:
    _, prepared, proposal = service.prepare_tool(
        "chemistry_molar_mass",
        {
            "formula": formula,
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    return service.confirm_and_execute(
        prepared, proposal, identity="m281-benchmark-confirmation"
    )


def _stats(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50": statistics.median(ordered),
        "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
        "p99": ordered[max(0, int(len(ordered) * 0.99) - 1)],
    }
