"""Unit-aware exact bounded affine solver for M-33 trusted runtime."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.capabilities.scalar_equation_solver import (
    NeedsNewCapability,
    ScalarEquationSolution,
    _affine,
)
from ai_brain.stage3.knowledge_ir.records import DimensionVector, RuleContent, UnitRef
from ai_brain.stage3.knowledge_ir.validation import (
    VariableSymbolTable,
    validate_expression,
)


class ApplicabilityNotSatisfied(ValueError):
    pass


@dataclass(frozen=True)
class TypedQuantity:
    value: str | int
    unit: UnitRef


@dataclass(frozen=True)
class UnitConversionReceipt:
    variable_id: str
    input_unit_id: str
    output_unit_id: str
    input_value: str
    output_value: str
    scale_numerator: int
    scale_denominator: int
    dimension: DimensionVector
    receipt_hash: str


@dataclass(frozen=True)
class TypedScalarEquationSolution:
    solution: ScalarEquationSolution
    output_unit_id: str | None
    conversion_receipts: tuple[UnitConversionReceipt, ...]


def solve_typed_scalar_equation(
    rule: RuleContent,
    known_values: dict[str, TypedQuantity | str | int],
    unknown: str,
    *,
    output_unit: UnitRef | None = None,
    satisfied_conditions: tuple[str, ...] = (),
    require_typed_quantities: bool = True,
) -> TypedScalarEquationSolution:
    symbols = VariableSymbolTable(rule.variables)
    if unknown not in symbols.bindings or set(known_values) != set(symbols.bindings) - {
        unknown
    }:
        raise NeedsNewCapability(
            "NEEDS_NEW_CAPABILITY: exactly one requested unknown is required"
        )
    missing = set(rule.applicability.preconditions) - set(satisfied_conditions)
    if missing:
        raise ApplicabilityNotSatisfied(
            "INSUFFICIENT_EVIDENCE: unresolved applicability conditions: "
            + ", ".join(sorted(missing))
        )
    converted: dict[str, str] = {}
    receipts = []
    for variable_id, value in known_values.items():
        binding = symbols.bindings[variable_id]
        quantity = binding.value_type.quantity_type
        if isinstance(value, TypedQuantity):
            if quantity is None or quantity.canonical_unit is None:
                raise NeedsNewCapability(
                    "NEEDS_NEW_CAPABILITY: typed input lacks a canonical quantity unit"
                )
            converted_value, receipt = _convert(
                variable_id, value.value, value.unit, quantity.canonical_unit
            )
            converted[variable_id] = converted_value
            receipts.append(receipt)
        else:
            if require_typed_quantities and quantity is not None:
                raise NeedsNewCapability(
                    "NEEDS_NEW_CAPABILITY: quantity input must bind an exact unit"
                )
            converted[variable_id] = str(value)
        _check_range(binding, Fraction(converted[variable_id]))
    validate_expression(
        rule.expression,
        symbols=symbols,
        required_capabilities={
            "generic.scalar_equation_solver.v1",
            "generic.typed_scalar_equation_solver.v1",
        },
    )
    left = _affine(rule.expression.children[0], converted, unknown)
    right = _affine(rule.expression.children[1], converted, unknown)
    coefficient = left[0] - right[0]
    constant = left[1] - right[1]
    if coefficient == 0:
        raise NeedsNewCapability(
            "NEEDS_NEW_CAPABILITY: equation has zero or multiple accepted solutions"
        )
    exact = -constant / coefficient
    binding = symbols.bindings[unknown]
    _check_range(binding, exact)
    quantity = binding.value_type.quantity_type
    canonical_unit = quantity.canonical_unit if quantity else None
    output_unit_id = canonical_unit.unit_id if canonical_unit else None
    if output_unit is not None:
        if canonical_unit is None:
            raise NeedsNewCapability(
                "NEEDS_NEW_CAPABILITY: unknown has no canonical quantity unit"
            )
        output, receipt = _convert(unknown, _exact(exact), canonical_unit, output_unit)
        receipts.append(receipt)
        exact = Fraction(output)
        output_unit_id = output_unit.unit_id
    dimension = (
        tuple(quantity.dimension.__dict__.values()) if quantity is not None else None
    )
    solution = ScalarEquationSolution(
        "SOLVED_EXACT",
        unknown,
        exact.numerator,
        exact.denominator,
        _exact(exact),
        dimension,
        (
            "verify dimensions and applicability",
            "convert known quantities to canonical units",
            "normalize affine sides",
            "isolate requested unknown",
            "verify exact substitution and output conversion",
        ),
    )
    return TypedScalarEquationSolution(solution, output_unit_id, tuple(receipts))


def _convert(variable_id, value, input_unit, output_unit):
    if input_unit.dimension != output_unit.dimension:
        raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: incompatible unit dimension")
    if input_unit.scale_denominator == 0 or output_unit.scale_numerator == 0:
        raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: invalid unit conversion scale")
    scale = Fraction(
        input_unit.scale_numerator * output_unit.scale_denominator,
        input_unit.scale_denominator * output_unit.scale_numerator,
    )
    converted = Fraction(str(value)) * scale
    body = {
        "variable_id": variable_id,
        "input_unit_id": input_unit.unit_id,
        "output_unit_id": output_unit.unit_id,
        "input_value": str(value),
        "output_value": _exact(converted),
        "scale_numerator": scale.numerator,
        "scale_denominator": scale.denominator,
        "dimension": input_unit.dimension,
    }
    return body["output_value"], UnitConversionReceipt(
        **body, receipt_hash=content_hash(body)
    )


def _check_range(binding, value):
    if binding.minimum is not None and value < Fraction(binding.minimum):
        raise ApplicabilityNotSatisfied(
            f"INSUFFICIENT_EVIDENCE: {binding.variable_id} violates minimum"
        )
    if binding.maximum is not None and value > Fraction(binding.maximum):
        raise ApplicabilityNotSatisfied(
            f"INSUFFICIENT_EVIDENCE: {binding.variable_id} violates maximum"
        )


def _exact(value: Fraction) -> str:
    return (
        str(value.numerator)
        if value.denominator == 1
        else f"{value.numerator}/{value.denominator}"
    )
