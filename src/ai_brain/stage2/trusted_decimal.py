"""Shared resource-bounded Decimal parsing and rendering for trusted runtimes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class DecimalLimits:
    max_raw_chars: int = 512
    max_coefficient_digits: int = 128
    max_absolute_exponent: int = 256
    max_scale: int = 256
    max_adjusted_exponent: int = 256
    max_rendered_chars: int = 512
    max_result_digits: int = 128
    context_precision: int = 256
    max_integer_bits: int = 4096
    max_abs: Decimal | None = None


class TrustedDecimalError(ValueError):
    def __init__(self, message: str, *, resource_limit: bool = False) -> None:
        super().__init__(message)
        self.resource_limit = resource_limit


DEFAULT_DECIMAL_LIMITS = DecimalLimits()


_DECIMAL_RE = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?(?:0|[1-9][0-9]*))?\Z"
)


def parse_bounded_decimal(
    value: Any,
    limits: DecimalLimits = DEFAULT_DECIMAL_LIMITS,
    *,
    nonnegative: bool = False,
    integer: bool = False,
) -> Decimal:
    """Parse only canonical trusted types without invoking arbitrary ``str``."""

    if isinstance(value, (bool, float)):
        raise TrustedDecimalError("bool and float are forbidden decimal inputs")
    if isinstance(value, int):
        if value.bit_length() > limits.max_integer_bits:
            raise TrustedDecimalError(
                "integer exceeds bit-length limit", resource_limit=True
            )
        text = str(value)
    elif isinstance(value, str):
        text = value
    elif isinstance(value, Decimal):
        result = value
        _validate_decimal(result, limits, result=False)
        return _validate_semantics(result, nonnegative=nonnegative, integer=integer)
    else:
        raise TrustedDecimalError("unsupported decimal input type")
    if not text or len(text) > limits.max_raw_chars:
        raise TrustedDecimalError(
            "decimal raw length exceeds limit", resource_limit=True
        )
    if _DECIMAL_RE.fullmatch(text) is None:
        raise TrustedDecimalError("invalid canonical decimal")
    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise TrustedDecimalError("invalid canonical decimal") from error
    _validate_decimal(result, limits, result=False)
    return _validate_semantics(result, nonnegative=nonnegative, integer=integer)


def render_bounded_decimal(
    value: Decimal,
    limits: DecimalLimits = DEFAULT_DECIMAL_LIMITS,
    *,
    preserve_trailing_zeros: bool = False,
) -> str:
    """Render fixed-point text only after proving its allocation is bounded."""

    if not isinstance(value, Decimal):
        raise TrustedDecimalError("rendering requires Decimal")
    _validate_decimal(value, limits, result=True)
    rendered = format(value, "f")
    if not preserve_trailing_zeros and "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-0"}:
        rendered = "0"
    if len(rendered) > limits.max_rendered_chars:
        raise TrustedDecimalError(
            "decimal rendered result exceeds limit", resource_limit=True
        )
    return rendered


def estimated_fixed_length(value: Decimal) -> int:
    item = value.as_tuple()
    digits = max(1, len(item.digits))
    exponent = int(item.exponent)
    sign = int(bool(item.sign))
    if exponent >= 0:
        return sign + digits + exponent
    point = digits + exponent
    if point > 0:
        return sign + digits + 1
    return sign + 2 + (-point) + digits


def _validate_decimal(value: Decimal, limits: DecimalLimits, *, result: bool) -> None:
    if not value.is_finite():
        raise TrustedDecimalError("NaN and infinity are forbidden")
    item = value.as_tuple()
    exponent = item.exponent
    if not isinstance(exponent, int):
        raise TrustedDecimalError("non-finite decimal exponent")
    digit_limit = limits.max_result_digits if result else limits.max_coefficient_digits
    if len(item.digits) > digit_limit:
        raise TrustedDecimalError(
            "decimal coefficient exceeds limit", resource_limit=True
        )
    if abs(exponent) > limits.max_absolute_exponent:
        raise TrustedDecimalError("decimal exponent exceeds limit", resource_limit=True)
    if max(0, -exponent) > limits.max_scale:
        raise TrustedDecimalError("decimal scale exceeds limit", resource_limit=True)
    if abs(value.adjusted()) > limits.max_adjusted_exponent:
        raise TrustedDecimalError(
            "decimal adjusted exponent exceeds limit", resource_limit=True
        )
    if estimated_fixed_length(value) > limits.max_rendered_chars:
        raise TrustedDecimalError(
            "decimal fixed rendering exceeds limit", resource_limit=True
        )
    if limits.max_abs is not None and abs(value) > limits.max_abs:
        raise TrustedDecimalError(
            "decimal absolute value exceeds limit", resource_limit=True
        )


def _validate_semantics(value: Decimal, *, nonnegative: bool, integer: bool) -> Decimal:
    if nonnegative and value < 0:
        raise TrustedDecimalError("negative values are forbidden")
    if integer and value != value.to_integral_value():
        raise TrustedDecimalError("integer decimal required")
    return value
