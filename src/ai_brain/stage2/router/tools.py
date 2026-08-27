"""Resource-bounded deterministic local tools."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import (
    Clamped,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from typing import Any

from ai_brain.stage2.trusted_decimal import (
    DecimalLimits,
    TrustedDecimalError,
    estimated_fixed_length,
    parse_bounded_decimal,
    render_bounded_decimal,
)


@dataclass(frozen=True)
class DecimalToolLimits:
    max_operands: int = 16
    max_raw_operand_chars: int = 512
    max_coefficient_digits: int = 128
    max_absolute_exponent: int = 256
    max_scale: int = 256
    max_adjusted_exponent: int = 256
    max_result_digits: int = 128
    max_rendered_chars: int = 512
    context_precision: int = 256


DECIMAL_TOOL_LIMITS = DecimalToolLimits()
MAX_OPERANDS = DECIMAL_TOOL_LIMITS.max_operands
MAX_DECIMAL_DIGITS = DECIMAL_TOOL_LIMITS.max_coefficient_digits
DECIMAL_INPUT_NORMALIZATION_POLICY = "canonical-decimal-v2"
DECIMAL_CONTEXT_POLICY = "decimal-context-traps-v2"
DECIMAL_RENDERING_POLICY = "bounded-fixed-canonical-v2"
DATE_PARSING_POLICY = "strict-iso-date-v2"
DATE_OUTPUT_POLICY = "integer-days-v2"
DATE_ALLOWED_MODES = ("ABSOLUTE", "SIGNED")

_DECIMAL_RE = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?(?:0|[1-9][0-9]*))?\Z"
)


class ToolInputError(ValueError):
    def __init__(self, message: str, *, code: str = "TOOL_ARGUMENT_INVALID") -> None:
        super().__init__(message)
        self.code = code


def validate_decimal_arguments(
    arguments: dict[str, Any], limits: DecimalToolLimits = DECIMAL_TOOL_LIMITS
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ToolInputError("decimal arguments must be an object")
    if set(arguments) != {"operation", "operands"}:
        raise ToolInputError("decimal arguments require exactly operation and operands")
    operation = arguments["operation"]
    if not isinstance(operation, str) or operation not in {
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
    }:
        raise ToolInputError("unsupported decimal operation")
    raw_operands = arguments["operands"]
    if not isinstance(raw_operands, (list, tuple)):
        raise ToolInputError("decimal operands must be an array")
    if not 2 <= len(raw_operands) <= limits.max_operands:
        raise ToolInputError(
            f"decimal operation requires 2..{limits.max_operands} operands",
            code="TOOL_RESOURCE_LIMIT_REJECTED",
        )
    if operation in {"SUBTRACT", "DIVIDE"} and len(raw_operands) != 2:
        raise ToolInputError(f"{operation} requires exactly two operands")
    operands = tuple(_decimal(item, limits) for item in raw_operands)
    if operation == "DIVIDE" and operands[1].is_zero():
        raise ToolInputError("division by zero")
    return {
        "operation": operation,
        "operands": [_render_decimal(item, limits) for item in operands],
    }


def validate_date_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ToolInputError("date arguments must be an object")
    if set(arguments) != {"start_date", "end_date", "mode"}:
        raise ToolInputError(
            "date arguments require exactly start_date, end_date and mode"
        )
    start_text = arguments["start_date"]
    end_text = arguments["end_date"]
    mode = arguments["mode"]
    if not isinstance(start_text, str) or not isinstance(end_text, str):
        raise ToolInputError("start_date and end_date must be ISO date strings")
    if not isinstance(mode, str) or mode not in DATE_ALLOWED_MODES:
        raise ToolInputError("date difference mode must be SIGNED or ABSOLUTE")
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except ValueError as error:
        raise ToolInputError("two valid ISO dates are required") from error
    if start.isoformat() != start_text or end.isoformat() != end_text:
        raise ToolInputError("dates must use canonical YYYY-MM-DD form")
    return {"start_date": start_text, "end_date": end_text, "mode": mode}


def decimal_arithmetic(arguments: dict[str, Any]) -> dict[str, Any]:
    canonical = validate_decimal_arguments(arguments)
    operation = canonical["operation"]
    operands = tuple(_decimal(item) for item in canonical["operands"])
    try:
        with localcontext() as context:
            context.prec = DECIMAL_TOOL_LIMITS.context_precision
            for signal in (
                InvalidOperation,
                DivisionByZero,
                Overflow,
                Underflow,
                Clamped,
            ):
                context.traps[signal] = True
            if operation == "ADD":
                result = sum(operands, Decimal(0))
            elif operation == "SUBTRACT":
                result = operands[0] - operands[1]
            elif operation == "MULTIPLY":
                result = Decimal(1)
                for operand in operands:
                    result *= operand
            else:
                result = operands[0] / operands[1]
    except DecimalException as error:
        raise ToolInputError(
            "decimal operation rejected by numeric policy",
            code="TOOL_RESOURCE_LIMIT_REJECTED",
        ) from error
    return {"result": _render_decimal(result), "operation": operation}


def date_difference(arguments: dict[str, Any]) -> dict[str, Any]:
    canonical = validate_date_arguments(arguments)
    start = date.fromisoformat(canonical["start_date"])
    end = date.fromisoformat(canonical["end_date"])
    days = (end - start).days
    mode = canonical["mode"]
    return {"days": abs(days) if mode == "ABSOLUTE" else days, "mode": mode}


def _decimal(value: Any, limits: DecimalToolLimits = DECIMAL_TOOL_LIMITS) -> Decimal:
    try:
        return parse_bounded_decimal(value, _shared_limits(limits))
    except TrustedDecimalError as error:
        raise ToolInputError(
            str(error),
            code="TOOL_RESOURCE_LIMIT_REJECTED"
            if error.resource_limit
            else "TOOL_ARGUMENT_INVALID",
        ) from error


def _validate_decimal_tuple(
    value: Decimal, limits: DecimalToolLimits = DECIMAL_TOOL_LIMITS
) -> None:
    if not value.is_finite():
        raise ToolInputError("NaN and infinity are forbidden")
    item = value.as_tuple()
    exponent = item.exponent
    if not isinstance(exponent, int):
        raise ToolInputError("non-finite decimal exponent")
    if len(item.digits) > limits.max_coefficient_digits:
        raise ToolInputError(
            "decimal coefficient exceeds digit limit",
            code="TOOL_RESOURCE_LIMIT_REJECTED",
        )
    if abs(exponent) > limits.max_absolute_exponent:
        raise ToolInputError(
            "decimal exponent exceeds limit", code="TOOL_RESOURCE_LIMIT_REJECTED"
        )
    if max(0, -exponent) > limits.max_scale:
        raise ToolInputError(
            "decimal scale exceeds limit", code="TOOL_RESOURCE_LIMIT_REJECTED"
        )
    if abs(value.adjusted()) > limits.max_adjusted_exponent:
        raise ToolInputError(
            "decimal adjusted exponent exceeds limit",
            code="TOOL_RESOURCE_LIMIT_REJECTED",
        )
    if _estimated_fixed_length(value) > limits.max_rendered_chars:
        raise ToolInputError(
            "decimal fixed rendering exceeds limit",
            code="TOOL_RESOURCE_LIMIT_REJECTED",
        )


def _estimated_fixed_length(value: Decimal) -> int:
    return estimated_fixed_length(value)


def _render_decimal(
    value: Decimal, limits: DecimalToolLimits = DECIMAL_TOOL_LIMITS
) -> str:
    try:
        return render_bounded_decimal(value, _shared_limits(limits))
    except TrustedDecimalError as error:
        raise ToolInputError(
            str(error),
            code="TOOL_RESOURCE_LIMIT_REJECTED"
            if error.resource_limit
            else "TOOL_ARGUMENT_INVALID",
        ) from error


def _shared_limits(limits: DecimalToolLimits) -> DecimalLimits:
    return DecimalLimits(
        max_raw_chars=limits.max_raw_operand_chars,
        max_coefficient_digits=limits.max_coefficient_digits,
        max_absolute_exponent=limits.max_absolute_exponent,
        max_scale=limits.max_scale,
        max_adjusted_exponent=limits.max_adjusted_exponent,
        max_rendered_chars=limits.max_rendered_chars,
        max_result_digits=limits.max_result_digits,
        context_precision=limits.context_precision,
        max_integer_bits=limits.max_raw_operand_chars * 4,
    )
