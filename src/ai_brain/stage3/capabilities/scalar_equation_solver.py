"""Exact bounded affine one-unknown equation solver."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ai_brain.stage3.knowledge_ir.records import Expression, ExpressionKind, RuleContent
from ai_brain.stage3.knowledge_ir.validation import (
    VariableSymbolTable,
    validate_expression,
)


class NeedsNewCapability(ValueError):
    pass


@dataclass(frozen=True)
class ScalarEquationSolution:
    status: str
    unknown: str
    numerator: int
    denominator: int
    exact_value: str
    dimension: tuple[int, ...] | None
    step_receipts: tuple[str, ...]


def solve_scalar_equation(
    rule: RuleContent, known_values: dict[str, str | int], unknown: str
) -> ScalarEquationSolution:
    symbols = VariableSymbolTable(rule.variables)
    if unknown not in symbols.bindings or set(known_values) != set(symbols.bindings) - {
        unknown
    }:
        raise NeedsNewCapability(
            "NEEDS_NEW_CAPABILITY: exactly one requested unknown is required"
        )
    expression = rule.expression
    validate_expression(
        expression,
        symbols=symbols,
        required_capabilities={"generic.scalar_equation_solver.v1"},
    )
    if expression.kind is not ExpressionKind.EQUAL or len(expression.children) != 2:
        raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: solver accepts one equality")
    left = _affine(expression.children[0], known_values, unknown)
    right = _affine(expression.children[1], known_values, unknown)
    coefficient = left[0] - right[0]
    constant = left[1] - right[1]
    if coefficient == 0:
        raise NeedsNewCapability(
            "NEEDS_NEW_CAPABILITY: equation has zero or multiple accepted solutions"
        )
    solution = -constant / coefficient
    quantity = symbols.bindings[unknown].value_type.quantity_type
    dimension = (
        tuple(quantity.dimension.__dict__.values()) if quantity is not None else None
    )
    exact = (
        str(solution.numerator)
        if solution.denominator == 1
        else f"{solution.numerator}/{solution.denominator}"
    )
    return ScalarEquationSolution(
        "SOLVED_EXACT",
        unknown,
        solution.numerator,
        solution.denominator,
        exact,
        dimension,
        (
            "normalize affine sides",
            "isolate requested unknown",
            "verify exact substitution",
        ),
    )


def _affine(
    expression: Expression, known: dict[str, str | int], unknown: str
) -> tuple[Fraction, Fraction]:
    if expression.kind is ExpressionKind.VARIABLE:
        name = str(expression.value)
        return (
            (Fraction(1), Fraction(0))
            if name == unknown
            else (Fraction(0), _fraction(known[name]))
        )
    if expression.kind is ExpressionKind.CONSTANT:
        if isinstance(expression.value, bool):
            raise NeedsNewCapability(
                "NEEDS_NEW_CAPABILITY: boolean constant in equation"
            )
        return Fraction(0), _fraction(expression.value)
    if expression.kind in {ExpressionKind.ADD, ExpressionKind.SUBTRACT}:
        left = _affine(expression.children[0], known, unknown)
        right = _affine(expression.children[1], known, unknown)
        sign = 1 if expression.kind is ExpressionKind.ADD else -1
        return left[0] + sign * right[0], left[1] + sign * right[1]
    if expression.kind is ExpressionKind.MULTIPLY:
        left = _affine(expression.children[0], known, unknown)
        right = _affine(expression.children[1], known, unknown)
        if left[0] and right[0]:
            raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: nonlinear product")
        return left[0] * right[1] + right[0] * left[1], left[1] * right[1]
    if expression.kind is ExpressionKind.DIVIDE:
        numerator = _affine(expression.children[0], known, unknown)
        denominator = _affine(expression.children[1], known, unknown)
        if denominator[0] or denominator[1] == 0:
            raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: variable or zero divisor")
        return numerator[0] / denominator[1], numerator[1] / denominator[1]
    if expression.kind is ExpressionKind.POWER:
        base = _affine(expression.children[0], known, unknown)
        exponent = expression.children[1].value
        if exponent == 1:
            return base
        if exponent == 0:
            return Fraction(0), Fraction(1)
        if base[0]:
            raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: nonlinear power")
        return Fraction(0), base[1] ** int(exponent)
    raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: unsupported symbolic operation")


def _fraction(value: str | int | bool | None) -> Fraction:
    if isinstance(value, bool) or value is None:
        raise NeedsNewCapability("NEEDS_NEW_CAPABILITY: nonnumeric exact value")
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise NeedsNewCapability(
            "NEEDS_NEW_CAPABILITY: invalid exact rational"
        ) from error
