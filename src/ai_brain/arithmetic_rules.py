from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ArithmeticOp = Literal["add", "sub"]
TraceFormat = Literal["answer", "scratchpad", "rfft", "state_machine"]


@dataclass(frozen=True)
class ArithmeticCase:
    op: ArithmeticOp
    a: int
    b: int

    @property
    def result(self) -> int:
        return self.a + self.b if self.op == "add" else self.a - self.b

    @property
    def op_token(self) -> str:
        return "ADD" if self.op == "add" else "SUB"

    @property
    def sign(self) -> str:
        return "+" if self.op == "add" else "-"

    @property
    def key(self) -> str:
        return f"{self.op}:{self.a}:{self.b}"

    @property
    def max_digits(self) -> int:
        return max(len(str(abs(self.a))), len(str(abs(self.b))))


def arithmetic_prompt(case: ArithmeticCase) -> str:
    return f"{case.op_token} {case.a} {case.sign} {case.b}"


def format_answer(case: ArithmeticCase) -> str:
    return f"FINAL {case.result}"


def format_trace(case: ArithmeticCase, trace_format: TraceFormat) -> str:
    if trace_format == "answer":
        return format_answer(case)
    if trace_format == "scratchpad":
        return _format_scratchpad(case)
    if trace_format == "rfft":
        return _format_rfft(case)
    if trace_format == "state_machine":
        return _format_state_machine(case)
    raise ValueError(f"Unknown trace format: {trace_format}")


def verify_trace(case: ArithmeticCase, text: str, trace_format: TraceFormat) -> bool:
    return _normalize_lines(text) == _normalize_lines(format_trace(case, trace_format))


def final_answer_from_trace(text: str) -> int | None:
    match = re.search(r"(?im)^\s*FINAL\s+(-?\d+)\s*$", text)
    return int(match.group(1)) if match else None


def trace_component_scores(
    case: ArithmeticCase,
    text: str,
    trace_format: TraceFormat,
) -> dict[str, bool | None]:
    expected = format_trace(case, trace_format)
    expected_lines = _normalize_lines(expected)
    predicted_lines = _normalize_lines(text)
    final_expected = final_answer_from_trace(expected)
    final_predicted = final_answer_from_trace(text)
    digit_expected = _final_digits(final_expected)
    digit_predicted = _final_digits(final_predicted)
    expected_state_lines = _state_lines(expected_lines)
    predicted_state_lines = _state_lines(predicted_lines)
    carry_borrow_exact = (
        None
        if not expected_state_lines
        else predicted_state_lines == expected_state_lines
    )
    return {
        "final_exact": final_expected is not None and final_predicted == final_expected,
        "full_trace_exact": predicted_lines == expected_lines,
        "digit_exact": digit_predicted == digit_expected,
        "carry_borrow_exact": carry_borrow_exact,
    }


def _format_scratchpad(case: ArithmeticCase) -> str:
    if case.op == "add":
        return _addition_trace(case, header="TRACE ADD")
    return _subtraction_trace(case, header="TRACE SUB")


def _format_rfft(case: ArithmeticCase) -> str:
    if case.op == "add":
        return "\n".join(
            (
                "RULE ADD",
                "R1 LSD",
                "R2 SUM_DIGITS_WITH_CARRY",
                "R3 WRITE_MOD10",
                "R4 CARRY_FLOOR10",
                "R5 MOVE_LEFT_UNTIL_DONE",
                _addition_trace(case, header="EXEC ADD"),
            )
        )
    return "\n".join(
        (
            "RULE SUB",
            "R1 LSD",
            "R2 SUB_DIGITS_WITH_BORROW",
            "R3 IF_NEG_ADD10_AND_BORROW",
            "R4 WRITE_DIGIT",
            "R5 MOVE_LEFT_UNTIL_DONE",
            _subtraction_trace(case, header="EXEC SUB"),
        )
    )


def _format_state_machine(case: ArithmeticCase) -> str:
    if case.op == "add":
        return _addition_trace(case, header="STATE ADD", compact_state=True)
    return _subtraction_trace(case, header="STATE SUB", compact_state=True)


def _addition_trace(
    case: ArithmeticCase,
    *,
    header: str,
    compact_state: bool = False,
) -> str:
    a_digits = _digits_lsd(case.a, case.max_digits)
    b_digits = _digits_lsd(case.b, case.max_digits)
    carry = 0
    out_digits: list[int] = []
    lines = [header]
    for step, (a_digit, b_digit) in enumerate(zip(a_digits, b_digits, strict=True)):
        total = a_digit + b_digit + carry
        out_digit = total % 10
        next_carry = total // 10
        out_digits.append(out_digit)
        if compact_state:
            lines.append(f"READ {a_digit} {b_digit} C{carry}")
            lines.append(f"WRITE {out_digit}")
            lines.append(f"CARRY {next_carry}")
            lines.append("MOVE")
        else:
            lines.append(f"D{step}: {a_digit}+{b_digit}+C{carry}={total}")
            lines.append(f"OUT_D{step} {out_digit}")
            lines.append(f"C {next_carry}")
        carry = next_carry
    if carry:
        out_digits.append(carry)
        lines.append("READ 0 0 C1" if compact_state else "FINAL_CARRY 1")
        lines.append("WRITE 1" if compact_state else "OUT_C 1")
        if compact_state:
            lines.append("CARRY 0")
    lines.append("HALT")
    lines.append(f"FINAL {_digits_to_int_lsd(out_digits)}")
    return "\n".join(lines)


def _subtraction_trace(
    case: ArithmeticCase,
    *,
    header: str,
    compact_state: bool = False,
) -> str:
    if case.a < case.b:
        raise ValueError("Subtraction traces require non-negative result")
    a_digits = _digits_lsd(case.a, case.max_digits)
    b_digits = _digits_lsd(case.b, case.max_digits)
    borrow = 0
    out_digits: list[int] = []
    lines = [header]
    for step, (a_digit, b_digit) in enumerate(zip(a_digits, b_digits, strict=True)):
        raw = a_digit - borrow - b_digit
        if raw < 0:
            out_digit = raw + 10
            next_borrow = 1
        else:
            out_digit = raw
            next_borrow = 0
        out_digits.append(out_digit)
        if compact_state:
            lines.append(f"READ {a_digit} {b_digit} B{borrow}")
            lines.append(f"WRITE {out_digit}")
            lines.append(f"BORROW {next_borrow}")
            lines.append("MOVE")
        else:
            lines.append(f"D{step}: {a_digit}-{b_digit}-B{borrow}={raw}")
            lines.append(f"OUT_D{step} {out_digit}")
            lines.append(f"B {next_borrow}")
        borrow = next_borrow
    lines.append("HALT")
    lines.append(f"FINAL {_digits_to_int_lsd(out_digits)}")
    return "\n".join(lines)


def _digits_lsd(value: int, width: int) -> list[int]:
    text = str(abs(value)).zfill(width)
    return [int(char) for char in reversed(text)]


def _digits_to_int_lsd(digits: list[int]) -> int:
    if not digits:
        return 0
    text = "".join(str(digit) for digit in reversed(digits)).lstrip("0")
    return int(text or "0")


def _normalize_lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def _final_digits(value: int | None) -> list[str]:
    return list(str(value)) if value is not None else []


def _state_lines(lines: list[str]) -> list[str]:
    prefixes = ("C ", "B ", "CARRY ", "BORROW ", "FINAL_CARRY")
    return [line for line in lines if line.startswith(prefixes)]
