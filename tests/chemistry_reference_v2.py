from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


def load_abridged_weights(source_path: Path) -> dict[str, Decimal]:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return {row["symbol"]: Decimal(row["abridged_value"]) for row in payload["weights"]}


def reference_molar_mass(
    composition: dict[str, int], weights: dict[str, Decimal]
) -> Decimal:
    return sum(
        (weights[symbol] * count for symbol, count in composition.items()),
        Decimal(0),
    )


def generated_formula_cases() -> tuple[tuple[str, dict[str, int]], ...]:
    left_symbols = ("H", "C", "N", "O", "Na")
    right_symbols = ("Cl", "S", "Ca", "Fe", "Cu")
    coefficient_pairs = ((1, 1), (2, 1), (1, 3), (4, 2))
    cases: list[tuple[str, dict[str, int]]] = []
    for left in left_symbols:
        for right in right_symbols:
            for left_count, right_count in coefficient_pairs:
                formula = (
                    f"{left}{_coefficient(left_count)}"
                    f"{right}{_coefficient(right_count)}"
                )
                cases.append((formula, {left: left_count, right: right_count}))
    return tuple(cases)


def _coefficient(value: int) -> str:
    return "" if value == 1 else str(value)
