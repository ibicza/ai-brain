"""Exact answer values, unit dimensions, and deterministic equivalence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from ai_brain.stage2.trusted_decimal import parse_bounded_decimal


@dataclass(frozen=True)
class UnitDefinition:
    canonical: str
    dimension: str
    to_base: Decimal


_UNITS = {
    "g": UnitDefinition("g", "MASS", Decimal(1)),
    "г": UnitDefinition("g", "MASS", Decimal(1)),
    "kg": UnitDefinition("kg", "MASS", Decimal(1000)),
    "кг": UnitDefinition("kg", "MASS", Decimal(1000)),
    "mol": UnitDefinition("mol", "AMOUNT", Decimal(1)),
    "моль": UnitDefinition("mol", "AMOUNT", Decimal(1)),
    "mmol": UnitDefinition("mmol", "AMOUNT", Decimal("0.001")),
    "ммоль": UnitDefinition("mmol", "AMOUNT", Decimal("0.001")),
    "g/mol": UnitDefinition("g/mol", "MOLAR_MASS", Decimal(1)),
    "г/моль": UnitDefinition("g/mol", "MOLAR_MASS", Decimal(1)),
    "kg/mol": UnitDefinition("kg/mol", "MOLAR_MASS", Decimal(1000)),
    "кг/моль": UnitDefinition("kg/mol", "MOLAR_MASS", Decimal(1000)),
    "entities": UnitDefinition("entities", "ENTITY_COUNT", Decimal(1)),
    "частиц": UnitDefinition("entities", "ENTITY_COUNT", Decimal(1)),
    "u": UnitDefinition("u", "ATOMIC_WEIGHT", Decimal(1)),
    "а.е.м.": UnitDefinition("u", "ATOMIC_WEIGHT", Decimal(1)),
}


def parse_unit(value: str) -> UnitDefinition:
    if not isinstance(value, str):
        raise TypeError("unit must be text")
    normalized = value.strip().replace(" ", "").casefold()
    try:
        return _UNITS[normalized]
    except KeyError as error:
        raise ValueError("unknown or malformed unit") from error


def convert_exact(value: Any, source_unit: str, target_unit: str) -> Decimal:
    source = parse_unit(source_unit)
    target = parse_unit(target_unit)
    if source.dimension != target.dimension:
        raise ValueError("unit dimensions differ")
    number = parse_bounded_decimal(value)
    with localcontext() as context:
        context.prec = 256
        return number * source.to_base / target.to_base


def numeric_equivalent(
    actual_value: Any,
    actual_unit: str,
    expected_value: Any,
    expected_unit: str,
) -> tuple[bool, bool]:
    actual = parse_bounded_decimal(actual_value)
    expected = parse_bounded_decimal(expected_value)
    converted = convert_exact(actual, actual_unit, expected_unit)
    return converted == expected, parse_unit(actual_unit).canonical != parse_unit(
        expected_unit
    ).canonical


def unit_dimension(unit: str) -> str:
    return parse_unit(unit).dimension
