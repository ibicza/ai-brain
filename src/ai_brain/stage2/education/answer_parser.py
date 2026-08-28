"""Strict bounded parsing for trusted structured student answers."""

from __future__ import annotations

import re
from typing import Any

from ai_brain.stage2.education.answers import parse_unit
from ai_brain.stage2.education.models import (
    AnswerParseStatus,
    StudentAnswer,
    StudentAnswerKind,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.trusted_decimal import (
    parse_bounded_decimal,
    render_bounded_decimal,
)

MAX_ANSWER_CHARS = 2048
_NUMBER = r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?(?:0|[1-9][0-9]*))?"
_NUMERIC_UNIT = re.compile(rf"^\s*({_NUMBER})\s*([^\d\s].*?)\s*$")
_INTERVAL = re.compile(rf"^\s*\[\s*({_NUMBER})\s*,\s*({_NUMBER})\s*\]\s*$")
_COUNT_ITEM = re.compile(r"^([A-Z][a-z]?)\s*(?::|=)\s*([0-9]+)$")


def parse_student_answer(
    raw: Any,
    answer_kind: StudentAnswerKind,
    *,
    supported_symbols: set[str] | frozenset[str] = frozenset(),
    confirmed: bool = False,
) -> StudentAnswer:
    raw_hash = _raw_input_hash(raw)
    try:
        interpreted, status = _parse(
            raw, answer_kind, supported_symbols=supported_symbols, confirmed=confirmed
        )
        issues: tuple[str, ...] = ()
    except (TypeError, ValueError) as error:
        interpreted = None
        status = AnswerParseStatus.INVALID
        issues = (str(error),)
    body = {
        "answer_kind": answer_kind,
        "raw_input_hash": raw_hash,
        "interpreted_answer": interpreted,
        "parse_status": status,
        "issues": issues,
        "confirmed": confirmed,
    }
    return StudentAnswer(**body, answer_hash=content_hash(body))


def _parse(
    raw: Any,
    kind: StudentAnswerKind,
    *,
    supported_symbols: set[str] | frozenset[str],
    confirmed: bool,
) -> tuple[dict[str, Any], AnswerParseStatus]:
    if isinstance(raw, (bool, float)):
        raise TypeError("bool and float answer inputs are forbidden")
    if kind == StudentAnswerKind.STEP_SEQUENCE:
        return _step_sequence(raw), AnswerParseStatus.PARSED
    if kind == StudentAnswerKind.FREE_TEXT_ASSISTIVE:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > MAX_ANSWER_CHARS:
            raise ValueError("invalid free-text answer")
        candidate = {"text": raw.strip()}
        return candidate, (
            AnswerParseStatus.PARSED
            if confirmed
            else AnswerParseStatus.REQUIRES_CONFIRMATION
        )
    if not isinstance(raw, (str, int)):
        raise TypeError("answer must be bounded text or integer")
    text = str(raw)
    if not text or len(text) > MAX_ANSWER_CHARS or "\x00" in text:
        raise ValueError("answer length is invalid")
    if kind == StudentAnswerKind.NUMERIC_WITH_UNIT:
        match = _NUMERIC_UNIT.fullmatch(text)
        if match is None:
            raise ValueError("expected one numeric value with one unit")
        unit = parse_unit(match.group(2))
        value = parse_bounded_decimal(match.group(1))
        return {
            "value": render_bounded_decimal(value),
            "unit": unit.canonical,
        }, AnswerParseStatus.PARSED
    if kind == StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL:
        match = _INTERVAL.fullmatch(text)
        if match is None:
            raise ValueError("expected a closed decimal interval")
        lower = parse_bounded_decimal(match.group(1))
        upper = parse_bounded_decimal(match.group(2))
        if lower > upper:
            raise ValueError("interval lower bound exceeds upper bound")
        return {
            "lower": render_bounded_decimal(lower),
            "upper": render_bounded_decimal(upper),
        }, AnswerParseStatus.PARSED
    if kind in {
        StudentAnswerKind.FORMULA_COMPOSITION,
        StudentAnswerKind.ELEMENT_COUNT_MAP,
    }:
        return {
            "element_counts": _count_map(text, supported_symbols)
        }, AnswerParseStatus.PARSED
    if kind == StudentAnswerKind.MULTIPLE_CHOICE:
        value = text.strip().upper()
        if re.fullmatch(r"[A-Z]", value) is None:
            raise ValueError("expected one multiple-choice letter")
        return {"choice": value}, AnswerParseStatus.PARSED
    raise ValueError("unsupported answer kind")


def _raw_input_hash(raw: Any) -> str:
    if isinstance(raw, float):
        safe_value: Any = raw.hex()
    elif isinstance(raw, (str, int, bool, tuple, list, dict)):
        safe_value = raw
    else:
        safe_value = "UNSUPPORTED_TYPE"
    try:
        return content_hash({"type": type(raw).__name__, "value": safe_value})
    except (TypeError, ValueError):
        return content_hash({"type": type(raw).__name__, "value": "INVALID"})


def _count_map(
    text: str, supported_symbols: set[str] | frozenset[str]
) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw_item in re.split(r"[,;]", text):
        match = _COUNT_ITEM.fullmatch(raw_item.strip())
        if match is None:
            raise ValueError("malformed element count map")
        symbol, count_text = match.groups()
        if supported_symbols and symbol not in supported_symbols:
            raise ValueError("unknown or wrong-case element symbol")
        if symbol in result:
            raise ValueError("duplicate element answer")
        count = int(count_text)
        if count <= 0 or count > 1_000_000:
            raise ValueError("element count is outside the bounded range")
        result[symbol] = count
    if not result:
        raise ValueError("empty element count map")
    return dict(sorted(result.items()))


def _step_sequence(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, (tuple, list)) or not raw or len(raw) > 64:
        raise ValueError("step sequence must contain 1..64 structured steps")
    steps = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "operation",
            "operands",
            "output",
            "unit",
        }:
            raise ValueError("step has an invalid schema")
        operation = item["operation"]
        operands = item["operands"]
        if not isinstance(operation, str) or not isinstance(operands, (tuple, list)):
            raise TypeError("step operation or operands are invalid")
        if len(operands) > 8:
            raise ValueError("too many step operands")
        parsed_operands = tuple(
            render_bounded_decimal(parse_bounded_decimal(value)) for value in operands
        )
        output = render_bounded_decimal(parse_bounded_decimal(item["output"]))
        unit = parse_unit(item["unit"]).canonical if item["unit"] else None
        steps.append(
            {
                "operation": operation.upper(),
                "operands": parsed_operands,
                "output": output,
                "unit": unit,
            }
        )
    return {"steps": tuple(steps)}
