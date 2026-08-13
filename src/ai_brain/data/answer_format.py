from __future__ import annotations

import re
from typing import Literal

from ai_brain.data.schema import TrainingExample

AnswerFormatName = Literal[
    "normal_answer",
    "digit_spaced",
    "scratchpad",
    "reversed_answer",
]

ANSWER_FORMAT_NAMES: tuple[AnswerFormatName, ...] = (
    "normal_answer",
    "digit_spaced",
    "scratchpad",
    "reversed_answer",
)

_CASE_PREFIX_RE = re.compile(r"case \d+\.")
_NUMBER_RE = re.compile(r"(?<![\w])\d+(?![\w])")


def apply_answer_format(
    example: TrainingExample,
    answer_format: AnswerFormatName = "normal_answer",
) -> TrainingExample:
    if answer_format == "normal_answer":
        return _with_format_metadata(example, answer_format)

    if answer_format == "digit_spaced":
        return _format_digit_spaced(example, answer_format)

    if answer_format == "scratchpad":
        return _format_scratchpad(example, answer_format)

    if answer_format == "reversed_answer":
        return _format_reversed_answer(example, answer_format)

    raise ValueError(f"Unknown answer format: {answer_format}")


def _format_digit_spaced(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> TrainingExample:
    return TrainingExample(
        id=example.id,
        task_type=example.task_type,
        prompt=_space_digits_in_text(example.prompt),
        answer=_space_digits_in_text(example.answer),
        metadata=_format_metadata(example, answer_format),
    )


def _format_scratchpad(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> TrainingExample:
    answer = _scratchpad_answer(example)
    return TrainingExample(
        id=example.id,
        task_type=example.task_type,
        prompt=example.prompt,
        answer=answer,
        metadata=_format_metadata(example, answer_format),
    )


def _format_reversed_answer(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> TrainingExample:
    if not example.answer.isdecimal():
        return _with_format_metadata(example, answer_format)

    return TrainingExample(
        id=example.id,
        task_type=example.task_type,
        prompt=example.prompt,
        answer=_space_digits(example.answer[::-1]),
        metadata=_format_metadata(example, answer_format),
    )


def _scratchpad_answer(example: TrainingExample) -> str:
    metadata = example.metadata

    if example.task_type == "arithmetic.add":
        return _addition_scratchpad(metadata["a"], metadata["b"], label_answer=True)

    if example.task_type == "arithmetic.subtract":
        return _subtraction_scratchpad(metadata["a"], metadata["b"], label_answer=True)

    if example.task_type == "arithmetic.missing_addend":
        a = metadata["a"]
        total = metadata["total"]
        missing = metadata["missing"]
        return "\n".join(
            [
                f"known: {a}",
                f"target: {total}",
                f"missing: {total} - {a} = {missing}",
                f"answer: {missing}",
            ]
        )

    if example.task_type == "arithmetic.double_step":
        a = metadata["a"]
        b = metadata["b"]
        c = metadata["c"]
        intermediate = a + b
        answer = intermediate - c
        return "\n".join(
            [
                f"step 1: {a} + {b} = {intermediate}",
                f"step 2: {intermediate} - {c} = {answer}",
                f"answer: {answer}",
            ]
        )

    if example.task_type == "state_change.add":
        start = metadata["start"]
        delta = metadata["delta"]
        return "\n".join(
            [
                f"start: {start}",
                f"change: +{delta}",
                *_addition_lines(start, delta),
                f"answer: {start + delta}",
            ]
        )

    if example.task_type == "state_change.subtract":
        start = metadata["start"]
        delta = metadata["delta"]
        return "\n".join(
            [
                f"start: {start}",
                f"change: -{delta}",
                *_subtraction_lines(start, delta),
                f"answer: {start - delta}",
            ]
        )

    if example.task_type in {"sorting.ascending", "sorting.descending"}:
        return _sorting_scratchpad(
            metadata["numbers"],
            reverse=example.task_type == "sorting.descending",
        )

    if example.answer.isdecimal():
        return f"given: {example.answer}\nanswer: {example.answer}"

    return example.answer


def _addition_scratchpad(a: int, b: int, *, label_answer: bool) -> str:
    lines = _addition_lines(a, b)
    final = f"answer: {a + b}" if label_answer else str(a + b)
    return "\n".join([*lines, final])


def _addition_lines(a: int, b: int) -> list[str]:
    places = ("ones", "tens", "hundreds", "thousands")
    digits_a = _reversed_digits(a)
    digits_b = _reversed_digits(b)
    max_digits = max(len(digits_a), len(digits_b))
    carry = 0
    lines: list[str] = []

    for index in range(max_digits):
        left = digits_a[index] if index < len(digits_a) else 0
        right = digits_b[index] if index < len(digits_b) else 0
        total = left + right + carry
        place = _place_name(index, places)
        carry_text = f" + carry {carry}" if carry else ""

        if total >= 10 and index < max_digits - 1:
            lines.append(
                f"{place}: {left} + {right}{carry_text} = {total}, "
                f"write {total % 10} carry {total // 10}"
            )
        else:
            lines.append(f"{place}: {left} + {right}{carry_text} = {total}")

        carry = total // 10

    if carry:
        lines.append(f"carry: {carry}")

    return lines


def _subtraction_scratchpad(a: int, b: int, *, label_answer: bool) -> str:
    lines = _subtraction_lines(a, b)
    final = f"answer: {a - b}" if label_answer else str(a - b)
    return "\n".join([*lines, final])


def _subtraction_lines(a: int, b: int) -> list[str]:
    places = ("ones", "tens", "hundreds", "thousands")
    digits_a = _reversed_digits(a)
    digits_b = _reversed_digits(b)
    max_digits = max(len(digits_a), len(digits_b))
    borrow = 0
    lines: list[str] = []

    for index in range(max_digits):
        top = digits_a[index] if index < len(digits_a) else 0
        bottom = digits_b[index] if index < len(digits_b) else 0
        adjusted_top = top - borrow
        next_borrow = 0
        place = _place_name(index, places)
        borrow_text = f" - borrow {borrow}" if borrow else ""

        if adjusted_top < bottom:
            adjusted_top += 10
            next_borrow = 1
            lines.append(
                f"{place}: {top}{borrow_text} needs borrow; "
                f"{adjusted_top} - {bottom} = {adjusted_top - bottom}"
            )
        else:
            lines.append(
                f"{place}: {top}{borrow_text} - {bottom} = {adjusted_top - bottom}"
            )

        borrow = next_borrow

    return lines


def _sorting_scratchpad(numbers: list[int], *, reverse: bool) -> str:
    remaining = list(numbers)
    ordered: list[int] = []
    selector_name = "largest" if reverse else "smallest"
    lines = [f"numbers: {_join_numbers(numbers)}"]

    while remaining:
        selected = max(remaining) if reverse else min(remaining)
        ordered.append(selected)
        remaining.remove(selected)
        lines.append(f"step {len(ordered)}: {selector_name} is {selected}")
        if remaining:
            lines.append(f"remaining: {_join_numbers(remaining)}")

    lines.append(f"answer: {_join_numbers(ordered)}")
    return "\n".join(lines)


def _space_digits_in_text(text: str) -> str:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__CASE_PREFIX_{len(protected) - 1}__"

    protected_text = _CASE_PREFIX_RE.sub(protect, text)
    spaced_text = _NUMBER_RE.sub(
        lambda match: _space_digits(match.group(0)), protected_text
    )

    for index, value in enumerate(protected):
        spaced_text = spaced_text.replace(f"__CASE_PREFIX_{index}__", value)

    return spaced_text


def _space_digits(value: str) -> str:
    return " ".join(value)


def _reversed_digits(value: int) -> list[int]:
    return [int(digit) for digit in str(value)[::-1]]


def _place_name(index: int, places: tuple[str, ...]) -> str:
    if index < len(places):
        return places[index]
    return f"10^{index}"


def _join_numbers(numbers: list[int]) -> str:
    return ", ".join(str(number) for number in numbers)


def _with_format_metadata(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> TrainingExample:
    return TrainingExample(
        id=example.id,
        task_type=example.task_type,
        prompt=example.prompt,
        answer=example.answer,
        metadata=_format_metadata(example, answer_format),
    )


def _format_metadata(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> dict[str, object]:
    metadata = dict(example.metadata)
    metadata["answer_format"] = answer_format

    if answer_format != "normal_answer":
        metadata["original_prompt"] = example.prompt
        metadata["original_answer"] = example.answer

    return metadata
