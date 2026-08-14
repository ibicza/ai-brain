from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import torch

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer

FEATURE_NONE_ID = 0

DIGIT_VALUE_VOCAB_SIZE = 11
DIGIT_PLACE_VOCAB_SIZE = 5
NUMBER_ROLE_VOCAB_SIZE = 8
OPERATION_STEP_VOCAB_SIZE = 9

DIGIT_PLACE_IDS = {
    "none": 0,
    "ones": 1,
    "tens": 2,
    "hundreds": 3,
    "carry": 4,
}

NUMBER_ROLE_IDS = {
    "none": 0,
    "a": 1,
    "b": 2,
    "carry_in": 3,
    "carry_out": 4,
    "borrow_in": 5,
    "borrow_out": 6,
    "result": 7,
}

OPERATION_STEP_IDS = {
    "none": 0,
    "prompt": 1,
    "digit_prompt": 2,
    "digit_answer": 3,
    "a_row": 4,
    "b_row": 5,
    "unit_step": 6,
    "tens_step": 7,
    "out": 8,
}

NUMERIC_FEATURE_KEYS = (
    "digit_value_ids",
    "digit_place_ids",
    "number_role_ids",
    "operation_step_ids",
)


@dataclass(frozen=True)
class NumericFeatureArrays:
    digit_value_ids: list[int]
    digit_place_ids: list[int]
    number_role_ids: list[int]
    operation_step_ids: list[int]

    @classmethod
    def none(cls, length: int) -> NumericFeatureArrays:
        zeros = [FEATURE_NONE_ID] * length
        return cls(
            digit_value_ids=list(zeros),
            digit_place_ids=list(zeros),
            number_role_ids=list(zeros),
            operation_step_ids=list(zeros),
        )

    def as_dict(self) -> dict[str, list[int]]:
        return {
            "digit_value_ids": self.digit_value_ids,
            "digit_place_ids": self.digit_place_ids,
            "number_role_ids": self.number_role_ids,
            "operation_step_ids": self.operation_step_ids,
        }


def encode_text_numeric_features(
    text: str,
    tokenizer: ByteLevelBpeTokenizer,
) -> tuple[list[int], NumericFeatureArrays]:
    encoded = tokenizer.encode_with_offsets(text)
    char_features = _classify_chars(text)
    token_features = NumericFeatureArrays.none(len(encoded.ids))

    for token_index, (start, end) in enumerate(encoded.offsets):
        if start >= end:
            continue
        span_features = char_features[start:end]
        token_features.digit_value_ids[token_index] = _majority_feature(
            feature[0] for feature in span_features
        )
        token_features.digit_place_ids[token_index] = _majority_feature(
            feature[1] for feature in span_features
        )
        token_features.number_role_ids[token_index] = _majority_feature(
            feature[2] for feature in span_features
        )
        token_features.operation_step_ids[token_index] = _majority_feature(
            feature[3] for feature in span_features
        )

    return encoded.ids, token_features


def build_numeric_feature_tensors(
    *,
    input_ids: list[int],
    text_without_bos: str,
    tokenizer: ByteLevelBpeTokenizer,
    device: torch.device,
) -> dict[str, torch.Tensor]:
    encoded_ids, encoded_features = encode_text_numeric_features(
        text_without_bos,
        tokenizer,
    )
    features = NumericFeatureArrays.none(len(input_ids))
    if input_ids[1:] == encoded_ids:
        for key, values in encoded_features.as_dict().items():
            getattr(features, key)[1:] = values
    return {
        key: torch.tensor([values], dtype=torch.long, device=device)
        for key, values in features.as_dict().items()
    }


def empty_numeric_feature_tensors(
    *,
    shape: torch.Size | tuple[int, int],
    device: torch.device,
) -> dict[str, torch.Tensor]:
    batch_size, sequence_length = int(shape[0]), int(shape[1])
    return {
        key: torch.zeros(
            (batch_size, sequence_length),
            dtype=torch.long,
            device=device,
        )
        for key in NUMERIC_FEATURE_KEYS
    }


def _classify_chars(text: str) -> list[tuple[int, int, int, int]]:
    features = [
        (FEATURE_NONE_ID, FEATURE_NONE_ID, FEATURE_NONE_ID, FEATURE_NONE_ID)
        for _ in text
    ]
    _mark_digit_prompts(text, features)
    _mark_composed_prompts(text, features)
    _mark_compact_trace_lines(text, features)
    return features


def _mark_digit_prompts(
    text: str,
    features: list[tuple[int, int, int, int]],
) -> None:
    for match in re.finditer(r"ADD_DIGIT a=(\d) b=(\d) c=(\d)", text):
        _mark_match_group(match, 1, features, "ones", "a", "digit_prompt")
        _mark_match_group(match, 2, features, "ones", "b", "digit_prompt")
        _mark_match_group(match, 3, features, "carry", "carry_in", "digit_prompt")
    for match in re.finditer(r"SUB_DIGIT a=(\d) b=(\d) borrow=(\d)", text):
        _mark_match_group(match, 1, features, "ones", "a", "digit_prompt")
        _mark_match_group(match, 2, features, "ones", "b", "digit_prompt")
        _mark_match_group(match, 3, features, "carry", "borrow_in", "digit_prompt")
    for match in re.finditer(r"S (\d)", text):
        _mark_match_group(match, 1, features, "ones", "result", "digit_answer")
    for match in re.finditer(r"C (\d)", text):
        _mark_match_group(match, 1, features, "carry", "carry_out", "digit_answer")
    for match in re.finditer(r"B (\d)", text):
        _mark_match_group(match, 1, features, "carry", "borrow_out", "digit_answer")


def _mark_composed_prompts(
    text: str,
    features: list[tuple[int, int, int, int]],
) -> None:
    for match in re.finditer(r"ADD2_COMPOSED (\d+) \+ (\d+)", text):
        _mark_number_span(match, 1, features, "a", "prompt")
        _mark_number_span(match, 2, features, "b", "prompt")
    for match in re.finditer(r"SUB2_COMPOSED (\d+) - (\d+)", text):
        _mark_number_span(match, 1, features, "a", "prompt")
        _mark_number_span(match, 2, features, "b", "prompt")


def _mark_compact_trace_lines(
    text: str,
    features: list[tuple[int, int, int, int]],
) -> None:
    is_subtraction = "OP SUB" in text
    for line_match in re.finditer(r"^.*$", text, flags=re.MULTILINE):
        line = line_match.group(0)
        offset = line_match.start()
        if line.startswith("A "):
            _mark_spaced_row(line, offset, features, "a", "a_row")
        elif line.startswith("B "):
            _mark_spaced_row(line, offset, features, "b", "b_row")
        elif line.startswith("U "):
            _mark_step_row(line, offset, features, "ones", "unit_step", is_subtraction)
        elif line.startswith("T "):
            _mark_step_row(line, offset, features, "tens", "tens_step", is_subtraction)
        elif line.startswith("OUT "):
            match = re.search(r"OUT (\d+)", line)
            if match:
                _mark_number_slice(
                    text,
                    features,
                    offset + match.start(1),
                    offset + match.end(1),
                    "result",
                    "out",
                )


def _mark_spaced_row(
    line: str,
    offset: int,
    features: list[tuple[int, int, int, int]],
    role: str,
    step: str,
) -> None:
    digits = list(re.finditer(r"\d", line))
    places = _places_for_count(len(digits))
    for digit_match, place in zip(digits, places, strict=True):
        _mark_char(
            features,
            offset + digit_match.start(),
            digit_match.group(0),
            place,
            role,
            step,
        )


def _mark_step_row(
    line: str,
    offset: int,
    features: list[tuple[int, int, int, int]],
    place: str,
    step: str,
    is_subtraction: bool,
) -> None:
    digits = list(re.finditer(r"\d", line))
    if not digits:
        return
    in_role = "borrow_in" if is_subtraction else "carry_in"
    out_role = "borrow_out" if is_subtraction else "carry_out"
    digit_specs = (
        ("a", place),
        ("b", place),
        (in_role, "carry"),
        ("result", place),
        (out_role, "carry"),
    )
    for digit_match, (role, digit_place) in zip(digits, digit_specs, strict=False):
        _mark_char(
            features,
            offset + digit_match.start(),
            digit_match.group(0),
            digit_place,
            role,
            step,
        )


def _mark_match_group(
    match: re.Match[str],
    group_index: int,
    features: list[tuple[int, int, int, int]],
    place: str,
    role: str,
    step: str,
) -> None:
    _mark_char(
        features,
        match.start(group_index),
        match.group(group_index),
        place,
        role,
        step,
    )


def _mark_number_span(
    match: re.Match[str],
    group_index: int,
    features: list[tuple[int, int, int, int]],
    role: str,
    step: str,
) -> None:
    _mark_number_slice(
        match.string,
        features,
        match.start(group_index),
        match.end(group_index),
        role,
        step,
    )


def _mark_number_slice(
    text: str,
    features: list[tuple[int, int, int, int]],
    start: int,
    end: int,
    role: str,
    step: str,
) -> None:
    digits = text[start:end]
    places = _places_for_count(len(digits))
    for offset, place in enumerate(places):
        _mark_char(features, start + offset, digits[offset], place, role, step)


def _mark_char(
    features: list[tuple[int, int, int, int]],
    index: int,
    digit: str,
    place: str,
    role: str,
    step: str,
) -> None:
    if not digit.isdigit():
        return
    features[index] = (
        int(digit) + 1,
        DIGIT_PLACE_IDS[place],
        NUMBER_ROLE_IDS[role],
        OPERATION_STEP_IDS[step],
    )


def _places_for_count(count: int) -> list[str]:
    names = ["ones", "tens", "hundreds"]
    reversed_places = [names[min(index, len(names) - 1)] for index in range(count)]
    return list(reversed(reversed_places))


def _majority_feature(values) -> int:
    non_none = [value for value in values if value != FEATURE_NONE_ID]
    if not non_none:
        return FEATURE_NONE_ID
    return Counter(non_none).most_common(1)[0][0]
