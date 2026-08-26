"""Bounded deterministic implementations for M-27 local read-only tools."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

MAX_OPERANDS = 16
MAX_DECIMAL_DIGITS = 128


class ToolInputError(ValueError):
    pass


def decimal_arithmetic(arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation", "")).upper()
    raw_operands = arguments.get("operands")
    if operation not in {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"}:
        raise ToolInputError("unsupported decimal operation")
    if (
        not isinstance(raw_operands, (list, tuple))
        or not 2 <= len(raw_operands) <= MAX_OPERANDS
    ):
        raise ToolInputError("decimal operation requires 2..16 operands")
    operands = tuple(_decimal(item) for item in raw_operands)
    if operation in {"SUBTRACT", "DIVIDE"} and len(operands) != 2:
        raise ToolInputError(f"{operation} requires exactly two operands")
    with localcontext() as context:
        context.prec = MAX_DECIMAL_DIGITS * 2
        if operation == "ADD":
            result = sum(operands, Decimal(0))
        elif operation == "SUBTRACT":
            result = operands[0] - operands[1]
        elif operation == "MULTIPLY":
            result = Decimal(1)
            for operand in operands:
                result *= operand
        else:
            if operands[1] == 0:
                raise ToolInputError("division by zero")
            result = operands[0] / operands[1]
    if not result.is_finite():
        raise ToolInputError("non-finite decimal result")
    rendered = format(result, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-0"}:
        rendered = "0"
    if len(rendered.replace("-", "").replace(".", "")) > MAX_DECIMAL_DIGITS:
        raise ToolInputError("decimal result exceeds digit limit")
    return {"result": rendered, "operation": operation}


def date_difference(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        start = date.fromisoformat(str(arguments["start_date"]))
        end = date.fromisoformat(str(arguments["end_date"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ToolInputError("two ISO dates are required") from error
    mode = str(arguments.get("mode", "ABSOLUTE")).upper()
    if mode not in {"SIGNED", "ABSOLUTE"}:
        raise ToolInputError("date difference mode must be SIGNED or ABSOLUTE")
    days = (end - start).days
    return {"days": abs(days) if mode == "ABSOLUTE" else days, "mode": mode}


def _decimal(value: Any) -> Decimal:
    text = str(value)
    if len(text) > MAX_DECIMAL_DIGITS + 3:
        raise ToolInputError("decimal operand exceeds digit limit")
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError) as error:
        raise ToolInputError("invalid decimal operand") from error
    if not result.is_finite():
        raise ToolInputError("NaN and infinity are forbidden")
    digits = len(result.as_tuple().digits)
    if digits > MAX_DECIMAL_DIGITS:
        raise ToolInputError("decimal operand exceeds digit limit")
    return result
