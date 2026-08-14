from __future__ import annotations

import re
from typing import Literal

from ai_brain.data.number_format import (
    digits_of_number,
    format_plain_digit_number,
    format_role_number,
    place_names_for_digits,
)
from ai_brain.data.schema import TrainingExample

AnswerFormatName = Literal[
    "normal_answer",
    "digit_spaced",
    "scratchpad",
    "reversed_answer",
    "canonical_numeric",
    "place_role_numeric",
    "r2l_numeric",
]

ANSWER_FORMAT_NAMES: tuple[AnswerFormatName, ...] = (
    "normal_answer",
    "digit_spaced",
    "scratchpad",
    "reversed_answer",
    "canonical_numeric",
    "place_role_numeric",
    "r2l_numeric",
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

    if answer_format == "canonical_numeric":
        return _format_canonical_numeric(example, answer_format)

    if answer_format == "place_role_numeric":
        return _format_place_role_numeric(example, answer_format)

    if answer_format == "r2l_numeric":
        return _format_r2l_numeric(example, answer_format)

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


def _format_r2l_numeric(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> TrainingExample:
    if not example.answer.isdecimal():
        return TrainingExample(
            id=example.id,
            task_type=example.task_type,
            prompt=_space_digits_in_text(example.prompt),
            answer=f"answer: {example.answer}",
            metadata=_format_metadata(example, answer_format),
        )

    return TrainingExample(
        id=example.id,
        task_type=example.task_type,
        prompt=_space_digits_in_text(example.prompt),
        answer="\n".join(
            [
                f"REV {_space_digits(example.answer[::-1])}",
                f"answer: {example.answer}",
            ]
        ),
        metadata=_format_metadata(example, answer_format),
    )


def _format_canonical_numeric(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> TrainingExample:
    return TrainingExample(
        id=example.id,
        task_type=example.task_type,
        prompt=example.prompt,
        answer=_canonical_numeric_answer(example),
        metadata=_format_metadata(example, answer_format),
    )


def _format_place_role_numeric(
    example: TrainingExample,
    answer_format: AnswerFormatName,
) -> TrainingExample:
    return TrainingExample(
        id=example.id,
        task_type=example.task_type,
        prompt=_place_role_prompt(example),
        answer=_place_role_numeric_answer(example),
        metadata=_format_metadata(example, answer_format),
    )


def _place_role_prompt(example: TrainingExample) -> str:
    metadata = example.metadata

    if example.task_type == "arithmetic.add":
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["a"], "A"), (metadata["b"], "B")],
        )

    if example.task_type == "arithmetic.subtract":
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["a"], "A"), (metadata["b"], "B")],
        )

    if example.task_type == "arithmetic.missing_addend":
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["a"], "KNOWN"), (metadata["total"], "TARGET")],
        )

    if example.task_type == "arithmetic.double_step":
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["a"], "A"), (metadata["b"], "B"), (metadata["c"], "C")],
        )

    if example.task_type == "arithmetic.compare_sum":
        if all(key in metadata for key in ("a", "b", "c", "d")):
            return _replace_prompt_numbers_by_roles(
                example.prompt,
                [
                    (metadata["a"], "LA"),
                    (metadata["b"], "LB"),
                    (metadata["c"], "RA"),
                    (metadata["d"], "RB"),
                ],
            )
        return example.prompt

    if example.task_type in {"state_change.add", "state_change.subtract"}:
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["start"], "START"), (metadata["delta"], "CHANGE")],
        )

    if example.task_type in {
        "state_change.other_subject_no_change",
        "state_change.other_object_no_change",
    }:
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["start"], "GIVEN"), (metadata["delta"], "CHANGE")],
        )

    if example.task_type == "state_change.insufficient_start":
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["delta"], "CHANGE")],
        )

    if example.task_type in {"sorting.ascending", "sorting.descending"}:
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(number, f"N{index}") for index, number in enumerate(metadata["numbers"])],
        )

    if example.task_type in {"quantity.direct", "quantity.location_direct"}:
        return _replace_prompt_numbers_by_roles(
            example.prompt,
            [(metadata["count"], "N")],
        )

    return example.prompt


def _place_role_numeric_answer(example: TrainingExample) -> str:
    metadata = example.metadata

    if example.task_type == "arithmetic.add":
        return _place_role_add(
            metadata["a"],
            metadata["b"],
            op="OP ADD",
            a_label="A",
            b_label="B",
            out_label="OUT",
        )

    if example.task_type == "arithmetic.subtract":
        return _place_role_sub(
            metadata["a"],
            metadata["b"],
            op="OP SUB",
            a_label="A",
            b_label="B",
            out_label="OUT",
        )

    if example.task_type == "arithmetic.missing_addend":
        total = metadata["total"]
        known = metadata["a"]
        return "\n".join(
            [
                "OP MISS_ADD",
                format_role_number("KNOWN", known),
                format_role_number("TARGET", total),
                "AS SUB TARGET KNOWN",
                *_place_role_sub_rows(total, known, a_label="TARGET", b_label="KNOWN"),
                format_role_number("OUT", total - known),
            ]
        )

    if example.task_type == "arithmetic.double_step":
        a = metadata["a"]
        b = metadata["b"]
        c = metadata["c"]
        mid = a + b
        answer = mid - c
        return "\n".join(
            [
                "OP DOUBLE",
                format_role_number("A", a),
                format_role_number("B", b),
                format_role_number("C", c),
                "STEP1 ADD",
                *_place_role_add_rows(a, b, a_label="A", b_label="B"),
                format_role_number("MID", mid),
                "STEP2 SUB",
                *_place_role_sub_rows(mid, c, a_label="MID", b_label="C"),
                format_role_number("OUT", answer),
            ]
        )

    if example.task_type == "arithmetic.compare_sum":
        if all(key in metadata for key in ("a", "b", "c", "d")):
            a = metadata["a"]
            b = metadata["b"]
            c = metadata["c"]
            d = metadata["d"]
            left = a + b
            right = c + d
            return "\n".join(
                [
                    "OP COMP_SUM",
                    "LEFT ADD",
                    format_role_number("LA", a),
                    format_role_number("LB", b),
                    *_place_role_add_rows(a, b, a_label="LA", b_label="LB"),
                    format_role_number("LEFT_OUT", left),
                    "RIGHT ADD",
                    format_role_number("RA", c),
                    format_role_number("RB", d),
                    *_place_role_add_rows(c, d, a_label="RA", b_label="RB"),
                    format_role_number("RIGHT_OUT", right),
                    _place_role_compare_line(left, right),
                    format_role_number("OUT", max(left, right)),
                ]
            )
        left = metadata["left"]
        right = metadata["right"]
        return "\n".join(
            [
                "OP COMP_SUM",
                format_role_number("LEFT_OUT", left),
                format_role_number("RIGHT_OUT", right),
                _place_role_compare_line(left, right),
                format_role_number("OUT", max(left, right)),
            ]
        )

    if example.task_type == "state_change.add":
        start = metadata["start"]
        delta = metadata["delta"]
        return "\n".join(
            [
                "OP STATE_ADD",
                "SUBJ SAME",
                "OBJ SAME",
                format_role_number("START", start),
                format_role_number("CHANGE", delta),
                *_place_role_add_rows(start, delta, a_label="START", b_label="CHANGE"),
                format_role_number("OUT", start + delta),
            ]
        )

    if example.task_type == "state_change.subtract":
        start = metadata["start"]
        delta = metadata["delta"]
        return "\n".join(
            [
                "OP STATE_SUB",
                "SUBJ SAME",
                "OBJ SAME",
                format_role_number("START", start),
                format_role_number("CHANGE", delta),
                *_place_role_sub_rows(start, delta, a_label="START", b_label="CHANGE"),
                format_role_number("OUT", start - delta),
            ]
        )

    if example.task_type == "state_change.other_subject_no_change":
        start = metadata["start"]
        return "\n".join(
            [
                "OP STATE_NO_CHANGE",
                "SUBJ DIFF",
                "OBJ SAME",
                format_role_number("GIVEN", start),
                format_role_number("OUT", start),
            ]
        )

    if example.task_type == "state_change.other_object_no_change":
        start = metadata["start"]
        return "\n".join(
            [
                "OP STATE_NO_CHANGE",
                "SUBJ SAME",
                "OBJ DIFF",
                format_role_number("GIVEN", start),
                format_role_number("OUT", start),
            ]
        )

    if example.task_type == "state_change.insufficient_start":
        return "\n".join(["OP STATE_UNKNOWN_START", f"OUT {example.answer}"])

    if example.task_type in {"sorting.ascending", "sorting.descending"}:
        return _place_role_sorting(
            metadata["numbers"],
            reverse=example.task_type == "sorting.descending",
        )

    if example.task_type == "quantity.direct":
        count = metadata["count"]
        return "\n".join(
            [
                "OP COPY_QTY",
                "SUBJ SAME",
                "OBJ SAME",
                format_role_number("N", count),
                format_role_number("OUT", count),
            ]
        )

    if example.task_type == "quantity.location_direct":
        count = metadata["count"]
        return "\n".join(
            [
                "OP COPY_LOC_QTY",
                "LOC SAME",
                "OBJ SAME",
                format_role_number("N", count),
                format_role_number("OUT", count),
            ]
        )

    if example.task_type == "quantity.known_zero":
        return "OP KNOWN_ZERO\nOUT_U 0"

    if example.answer.isdecimal():
        return f"OP COPY_NUM\n{format_role_number('OUT', int(example.answer))}"

    return f"OP TEXT\nOUT {example.answer}"


def _replace_prompt_numbers_by_roles(
    prompt: str,
    replacements: list[tuple[int, str]],
) -> str:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__CASE_PREFIX_{len(protected) - 1}__"

    replacement_index = 0
    protected_prompt = _CASE_PREFIX_RE.sub(protect, prompt)

    def replace_number(match: re.Match[str]) -> str:
        nonlocal replacement_index
        if replacement_index >= len(replacements):
            return match.group(0)

        value, role = replacements[replacement_index]
        if int(match.group(0)) != value:
            return match.group(0)

        replacement_index += 1
        return format_role_number(role, value)

    transformed = _NUMBER_RE.sub(replace_number, protected_prompt)
    for index, value in enumerate(protected):
        transformed = transformed.replace(f"__CASE_PREFIX_{index}__", value)
    return transformed


def _place_role_add(
    a: int,
    b: int,
    *,
    op: str,
    a_label: str,
    b_label: str,
    out_label: str,
) -> str:
    return "\n".join(
        [
            op,
            format_role_number(a_label, a),
            format_role_number(b_label, b),
            *_place_role_add_rows(a, b, a_label=a_label, b_label=b_label),
            format_role_number(out_label, a + b),
        ]
    )


def _place_role_add_rows(a: int, b: int, *, a_label: str, b_label: str) -> list[str]:
    max_digits = max(len(digits_of_number(a)), len(digits_of_number(b)))
    carry = 0
    rows: list[str] = []
    for index in range(max_digits):
        place = _place_for_lsd_index(index, max_digits)
        left = _digit_from_right(a, index)
        right = _digit_from_right(b, index)
        total = left + right + carry
        digit = total % 10
        next_carry = total // 10
        rows.append(
            f"P_{place} {a_label}_{place} {left} {b_label}_{place} {right} "
            f"C_IN {carry} -> S_{place} {digit} C_OUT {next_carry}"
        )
        carry = next_carry
    return rows


def _place_role_sub(
    a: int,
    b: int,
    *,
    op: str,
    a_label: str,
    b_label: str,
    out_label: str,
) -> str:
    return "\n".join(
        [
            op,
            format_role_number(a_label, a),
            format_role_number(b_label, b),
            *_place_role_sub_rows(a, b, a_label=a_label, b_label=b_label),
            format_role_number(out_label, a - b),
        ]
    )


def _place_role_sub_rows(a: int, b: int, *, a_label: str, b_label: str) -> list[str]:
    max_digits = max(len(digits_of_number(a)), len(digits_of_number(b)))
    borrow = 0
    rows: list[str] = []
    for index in range(max_digits):
        place = _place_for_lsd_index(index, max_digits)
        top = _digit_from_right(a, index)
        bottom = _digit_from_right(b, index)
        adjusted_top = top - borrow
        next_borrow = 0
        if adjusted_top < bottom:
            adjusted_top += 10
            next_borrow = 1
        rows.append(
            f"P_{place} {a_label}_{place} {top} {b_label}_{place} {bottom} "
            f"B_IN {borrow} -> S_{place} {adjusted_top - bottom} B_OUT {next_borrow}"
        )
        borrow = next_borrow
    return rows


def _place_role_compare_line(left: int, right: int) -> str:
    operator = ">" if left > right else "<"
    return (
        "COMPARE "
        f"{format_role_number('LEFT_OUT', left)} {operator} "
        f"{format_role_number('RIGHT_OUT', right)}"
    )


def _place_role_sorting(numbers: list[int], *, reverse: bool) -> str:
    ordered_pairs = sorted(
        enumerate(numbers),
        key=lambda item: item[1],
        reverse=reverse,
    )
    ordered_numbers = [number for _, number in ordered_pairs]
    op = "OP SORT_DESC" if reverse else "OP SORT_ASC"
    selector = "MAX" if reverse else "MIN"
    return "\n".join(
        [
            op,
            " | ".join(
                format_role_number(f"N{index}", number)
                for index, number in enumerate(numbers)
            ),
            *(
                f"S{rank} {selector} {format_role_number(f'N{index}', number)}"
                for rank, (index, number) in enumerate(ordered_pairs)
            ),
            f"OUT {_join_numbers(ordered_numbers)}",
        ]
    )


def _digit_from_right(value: int, index: int) -> int:
    digits = digits_of_number(value)
    offset = len(digits) - 1 - index
    if offset < 0:
        return 0
    return digits[offset]


def _place_for_lsd_index(index: int, num_digits: int) -> str:
    places = place_names_for_digits(num_digits)
    return places[-1 - index]


def _canonical_numeric_answer(example: TrainingExample) -> str:
    metadata = example.metadata

    if example.task_type == "arithmetic.add":
        return _canonical_add(
            metadata["a"],
            metadata["b"],
            op="OP ADD",
            a_label="A",
            b_label="B",
            out_label="OUT",
        )

    if example.task_type == "arithmetic.subtract":
        return _canonical_sub(
            metadata["a"],
            metadata["b"],
            op="OP SUB",
            a_label="A",
            b_label="B",
            out_label="OUT",
        )

    if example.task_type == "arithmetic.missing_addend":
        total = metadata["total"]
        known = metadata["a"]
        return "\n".join(
            [
                "OP MISS_ADD",
                f"KNOWN {_spaced_number(known)}",
                f"TARGET {_spaced_number(total)}",
                "AS SUB TARGET KNOWN",
                *_canonical_sub_rows(total, known),
                f"OUT {_spaced_number(total - known)}",
            ]
        )

    if example.task_type == "arithmetic.double_step":
        a = metadata["a"]
        b = metadata["b"]
        c = metadata["c"]
        mid = a + b
        answer = mid - c
        return "\n".join(
            [
                "OP DOUBLE",
                f"A {_spaced_number(a)}",
                f"B {_spaced_number(b)}",
                f"C {_spaced_number(c)}",
                "STEP1 ADD",
                *_canonical_add_rows(a, b),
                f"MID {_spaced_number(mid)}",
                "STEP2 SUB",
                *_canonical_sub_rows(mid, c),
                f"OUT {_spaced_number(answer)}",
            ]
        )

    if example.task_type == "arithmetic.compare_sum":
        if all(key in metadata for key in ("a", "b", "c", "d")):
            a = metadata["a"]
            b = metadata["b"]
            c = metadata["c"]
            d = metadata["d"]
            left = a + b
            right = c + d
            return "\n".join(
                [
                    "OP COMP_SUM",
                    "LEFT ADD",
                    f"A {_spaced_number(a)}",
                    f"B {_spaced_number(b)}",
                    *_canonical_add_rows(a, b),
                    f"LEFT_OUT {_spaced_number(left)}",
                    "RIGHT ADD",
                    f"A {_spaced_number(c)}",
                    f"B {_spaced_number(d)}",
                    *_canonical_add_rows(c, d),
                    f"RIGHT_OUT {_spaced_number(right)}",
                    _canonical_compare_line(left, right),
                    f"OUT {_spaced_number(max(left, right))}",
                ]
            )
        left = metadata["left"]
        right = metadata["right"]
        return "\n".join(
            [
                "OP COMP_SUM",
                f"LEFT_OUT {_spaced_number(left)}",
                f"RIGHT_OUT {_spaced_number(right)}",
                _canonical_compare_line(left, right),
                f"OUT {_spaced_number(max(left, right))}",
            ]
        )

    if example.task_type == "state_change.add":
        start = metadata["start"]
        delta = metadata["delta"]
        return "\n".join(
            [
                "OP STATE_ADD",
                "SUBJ SAME",
                "OBJ SAME",
                f"START {_spaced_number(start)}",
                f"CHANGE {_spaced_number(delta)}",
                *_canonical_add_rows(start, delta),
                f"OUT {_spaced_number(start + delta)}",
            ]
        )

    if example.task_type == "state_change.subtract":
        start = metadata["start"]
        delta = metadata["delta"]
        return "\n".join(
            [
                "OP STATE_SUB",
                "SUBJ SAME",
                "OBJ SAME",
                f"START {_spaced_number(start)}",
                f"CHANGE {_spaced_number(delta)}",
                *_canonical_sub_rows(start, delta),
                f"OUT {_spaced_number(start - delta)}",
            ]
        )

    if example.task_type == "state_change.other_subject_no_change":
        start = metadata["start"]
        return "\n".join(
            [
                "OP STATE_NO_CHANGE",
                "SUBJ DIFF",
                "OBJ SAME",
                f"GIVEN {_spaced_number(start)}",
                f"OUT {_spaced_number(start)}",
            ]
        )

    if example.task_type == "state_change.other_object_no_change":
        start = metadata["start"]
        return "\n".join(
            [
                "OP STATE_NO_CHANGE",
                "SUBJ SAME",
                "OBJ DIFF",
                f"GIVEN {_spaced_number(start)}",
                f"OUT {_spaced_number(start)}",
            ]
        )

    if example.task_type == "state_change.insufficient_start":
        return "\n".join(["OP STATE_UNKNOWN_START", f"OUT {example.answer}"])

    if example.task_type in {"sorting.ascending", "sorting.descending"}:
        return _canonical_sorting(
            metadata["numbers"],
            reverse=example.task_type == "sorting.descending",
        )

    if example.task_type == "quantity.direct":
        count = metadata["count"]
        return "\n".join(
            [
                "OP COPY_QTY",
                "SUBJ SAME",
                "OBJ SAME",
                f"N {_spaced_number(count)}",
                f"OUT {_spaced_number(count)}",
            ]
        )

    if example.task_type == "quantity.location_direct":
        count = metadata["count"]
        return "\n".join(
            [
                "OP COPY_LOC_QTY",
                "LOC SAME",
                "OBJ SAME",
                f"N {_spaced_number(count)}",
                f"OUT {_spaced_number(count)}",
            ]
        )

    if example.task_type == "quantity.known_zero":
        return "OP KNOWN_ZERO\nOUT 0"

    if example.answer.isdecimal():
        return f"OP COPY_NUM\nOUT {_spaced_number(int(example.answer))}"

    return f"OP TEXT\nOUT {example.answer}"


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


def _canonical_add(
    a: int,
    b: int,
    *,
    op: str,
    a_label: str,
    b_label: str,
    out_label: str,
) -> str:
    return "\n".join(
        [
            op,
            f"{a_label} {_spaced_number(a)}",
            f"{b_label} {_spaced_number(b)}",
            *_canonical_add_rows(a, b),
            f"{out_label} {_spaced_number(a + b)}",
        ]
    )


def _canonical_add_rows(a: int, b: int) -> list[str]:
    digits_a = _reversed_digits(a)
    digits_b = _reversed_digits(b)
    carry = 0
    rows: list[str] = []
    for index in range(max(len(digits_a), len(digits_b))):
        left = digits_a[index] if index < len(digits_a) else 0
        right = digits_b[index] if index < len(digits_b) else 0
        total = left + right + carry
        digit = total % 10
        next_carry = total // 10
        rows.append(f"P{index} {left} {right} C{carry} -> S{digit} C{next_carry}")
        carry = next_carry
    return rows


def _canonical_sub(
    a: int,
    b: int,
    *,
    op: str,
    a_label: str,
    b_label: str,
    out_label: str,
) -> str:
    return "\n".join(
        [
            op,
            f"{a_label} {_spaced_number(a)}",
            f"{b_label} {_spaced_number(b)}",
            *_canonical_sub_rows(a, b),
            f"{out_label} {_spaced_number(a - b)}",
        ]
    )


def _canonical_sub_rows(a: int, b: int) -> list[str]:
    digits_a = _reversed_digits(a)
    digits_b = _reversed_digits(b)
    borrow = 0
    rows: list[str] = []
    for index in range(max(len(digits_a), len(digits_b))):
        top = digits_a[index] if index < len(digits_a) else 0
        bottom = digits_b[index] if index < len(digits_b) else 0
        adjusted_top = top - borrow
        next_borrow = 0
        if adjusted_top < bottom:
            adjusted_top += 10
            next_borrow = 1
        rows.append(
            f"P{index} {top} {bottom} B{borrow} -> "
            f"S{adjusted_top - bottom} B{next_borrow}"
        )
        borrow = next_borrow
    return rows


def _canonical_compare_line(left: int, right: int) -> str:
    operator = ">" if left > right else "<"
    return f"COMPARE {_spaced_number(left)} {operator} {_spaced_number(right)}"


def _canonical_sorting(numbers: list[int], *, reverse: bool) -> str:
    ordered = sorted(numbers, reverse=reverse)
    op = "OP SORT_DESC" if reverse else "OP SORT_ASC"
    selector = "MAX" if reverse else "MIN"
    return "\n".join(
        [
            op,
            "N " + " | ".join(_spaced_number(number) for number in numbers),
            *(
                f"S{index} {selector} {_spaced_number(number)}"
                for index, number in enumerate(ordered)
            ),
            f"OUT {_join_numbers(ordered)}",
        ]
    )


def _spaced_number(value: int) -> str:
    return format_plain_digit_number(value)


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
