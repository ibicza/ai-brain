from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass

import torch

from ai_brain.language.tokenizer.bpe_tokenizer import (
    ByteLevelBpeTokenizer,
    NumericTokenizationMode,
)
from ai_brain.numeric_features import FEATURE_NONE_ID

POSITION_FEATURE_VOCAB_SIZE = 512
POSITION_FEATURE_KEYS = ("abacus_position_ids", "coupled_position_ids")


@dataclass(frozen=True)
class NumericPositionFeatureArrays:
    abacus_position_ids: list[int]
    coupled_position_ids: list[int]

    @classmethod
    def none(cls, length: int) -> NumericPositionFeatureArrays:
        zeros = [FEATURE_NONE_ID] * length
        return cls(
            abacus_position_ids=list(zeros),
            coupled_position_ids=list(zeros),
        )

    def as_dict(self) -> dict[str, list[int]]:
        return {
            "abacus_position_ids": self.abacus_position_ids,
            "coupled_position_ids": self.coupled_position_ids,
        }


def encode_text_position_features(
    text: str,
    tokenizer: ByteLevelBpeTokenizer,
    *,
    numeric_tokenization: NumericTokenizationMode = "default_bpe",
    abacus_offset: int = 0,
    coupled_offset: int = 0,
) -> tuple[list[int], NumericPositionFeatureArrays]:
    if abacus_offset < 0:
        raise ValueError("abacus_offset must be non-negative")
    if coupled_offset < 0:
        raise ValueError("coupled_offset must be non-negative")

    encoded = tokenizer.encode_with_offsets(
        text,
        numeric_tokenization=numeric_tokenization,
    )
    char_features = _classify_position_chars(
        text,
        abacus_offset=abacus_offset,
        coupled_offset=coupled_offset,
    )
    token_features = NumericPositionFeatureArrays.none(len(encoded.ids))

    for token_index, (start, end) in enumerate(encoded.offsets):
        if start >= end:
            continue
        span_features = char_features[start:end]
        token_features.abacus_position_ids[token_index] = _majority_feature(
            feature[0] for feature in span_features
        )
        token_features.coupled_position_ids[token_index] = _majority_feature(
            feature[1] for feature in span_features
        )

    return encoded.ids, token_features


def build_position_feature_tensors(
    *,
    input_ids: list[int],
    text_without_bos: str,
    tokenizer: ByteLevelBpeTokenizer,
    numeric_tokenization: NumericTokenizationMode,
    device: torch.device,
) -> dict[str, torch.Tensor]:
    encoded_ids, encoded_features = encode_text_position_features(
        text_without_bos,
        tokenizer,
        numeric_tokenization=numeric_tokenization,
    )
    features = NumericPositionFeatureArrays.none(len(input_ids))
    if input_ids[1:] == encoded_ids:
        for key, values in encoded_features.as_dict().items():
            getattr(features, key)[1:] = values
    return {
        key: torch.tensor([values], dtype=torch.long, device=device)
        for key, values in features.as_dict().items()
    }


def random_abacus_offset(*, max_offset: int, seed: int, index: int) -> int:
    return random_position_offset(max_offset=max_offset, seed=seed, index=index)


def random_position_offset(*, max_offset: int, seed: int, index: int) -> int:
    if max_offset <= 0:
        return 0
    return random.Random(seed + index).randint(0, max_offset)


def _classify_position_chars(
    text: str,
    *,
    abacus_offset: int,
    coupled_offset: int,
) -> list[tuple[int, int]]:
    features = [(FEATURE_NONE_ID, FEATURE_NONE_ID) for _ in text]
    _mark_abacus_digit_spans(text, features, abacus_offset=abacus_offset)
    _mark_coupled_default_digit_spans(text, features)
    _mark_coupled_compact_trace_rows(text, features)
    _mark_official_abacus_addition(text, features, abacus_offset=abacus_offset)
    _mark_official_position_coupling_addition(
        text,
        features,
        coupled_offset=coupled_offset,
    )
    return features


def _mark_abacus_digit_spans(
    text: str,
    features: list[tuple[int, int]],
    *,
    abacus_offset: int,
) -> None:
    for match in re.finditer(r"\d+", text):
        _mark_digit_span(
            features,
            start=match.start(),
            end=match.end(),
            feature_index=0,
            offset=abacus_offset,
        )


def _mark_coupled_default_digit_spans(
    text: str,
    features: list[tuple[int, int]],
) -> None:
    for match in re.finditer(r"\d+", text):
        _mark_digit_span(
            features,
            start=match.start(),
            end=match.end(),
            feature_index=1,
            offset=0,
        )


def _mark_coupled_compact_trace_rows(
    text: str,
    features: list[tuple[int, int]],
) -> None:
    for line_match in re.finditer(r"^.*$", text, flags=re.MULTILINE):
        line = line_match.group(0)
        offset = line_match.start()
        if line.startswith("U "):
            _mark_step_row_digits(line, offset, features, place_index=0)
        elif line.startswith("T "):
            _mark_step_row_digits(line, offset, features, place_index=1)


def _mark_step_row_digits(
    line: str,
    offset: int,
    features: list[tuple[int, int]],
    *,
    place_index: int,
) -> None:
    digits = list(re.finditer(r"\d", line))
    if not digits:
        return
    position_ids = (
        _position_id(place_index),
        _position_id(place_index),
        _position_id(place_index),
        _position_id(place_index),
        _position_id(place_index + 1),
    )
    for digit_match, position_id in zip(digits, position_ids, strict=False):
        _set_feature(
            features,
            offset + digit_match.start(),
            feature_index=1,
            value=position_id,
        )


def _mark_official_abacus_addition(
    text: str,
    features: list[tuple[int, int]],
    *,
    abacus_offset: int,
) -> None:
    for line_match in re.finditer(r"^.*$", text, flags=re.MULTILINE):
        line = line_match.group(0)
        if "ADD_ABACUS" not in line and not re.fullmatch(r"\s*=\s*\d+\s*", line):
            continue
        offset = line_match.start()
        for number_match in re.finditer(r"\d+", line):
            _mark_digit_span_left_to_right(
                features,
                start=offset + number_match.start(),
                end=offset + number_match.end(),
                feature_index=0,
                offset=abacus_offset,
            )


def _mark_official_position_coupling_addition(
    text: str,
    features: list[tuple[int, int]],
    *,
    coupled_offset: int,
) -> None:
    for match in re.finditer(
        r"ADD_PC\s+(?P<a>\d+)\s*(?P<plus>\+)\s*(?P<b>\d+)",
        text,
    ):
        start_position = 1 + coupled_offset
        _set_feature(
            features,
            match.start("plus"),
            feature_index=1,
            value=_position_id(start_position - 1),
        )
        _mark_pc_operand(
            features,
            start=match.start("a"),
            end=match.end("a"),
            start_position=start_position,
        )
        _mark_pc_operand(
            features,
            start=match.start("b"),
            end=match.end("b"),
            start_position=start_position,
        )

    for line_match in re.finditer(
        r"^\s*(?P<equals>=)\s*(?P<digits>\d(?:\s+\d)*)\s*$",
        text,
        flags=re.MULTILINE,
    ):
        start_position = 1 + coupled_offset
        equals_index = line_match.start("equals")
        _set_feature(
            features,
            equals_index,
            feature_index=1,
            value=_position_id(start_position - 1),
        )
        digits_start = line_match.start("digits")
        digit_matches = list(
            re.finditer(
                r"\d",
                text[digits_start : line_match.end("digits")],
            )
        )
        for index, digit_match in enumerate(digit_matches, start=1):
            _set_feature(
                features,
                digits_start + digit_match.start(),
                feature_index=1,
                value=_position_id(start_position - 1 + index),
            )


def _mark_pc_operand(
    features: list[tuple[int, int]],
    *,
    start: int,
    end: int,
    start_position: int,
) -> None:
    count = end - start
    for char_index in range(start, end):
        left_to_right_index = char_index - start
        paper_position = start_position + count - left_to_right_index
        _set_feature(
            features,
            char_index,
            feature_index=1,
            value=_position_id(paper_position - 1),
        )


def _mark_digit_span_left_to_right(
    features: list[tuple[int, int]],
    *,
    start: int,
    end: int,
    feature_index: int,
    offset: int,
) -> None:
    for char_index in range(start, end):
        position_from_left = char_index - start
        _set_feature(
            features,
            char_index,
            feature_index=feature_index,
            value=_position_id(position_from_left + offset),
        )


def _mark_digit_span(
    features: list[tuple[int, int]],
    *,
    start: int,
    end: int,
    feature_index: int,
    offset: int,
) -> None:
    count = end - start
    for char_index in range(start, end):
        place_from_right = count - 1 - (char_index - start)
        _set_feature(
            features,
            char_index,
            feature_index=feature_index,
            value=_position_id(place_from_right + offset),
        )


def _position_id(position: int) -> int:
    value = position + 1
    if value >= POSITION_FEATURE_VOCAB_SIZE:
        raise ValueError(
            "numeric position id exceeds POSITION_FEATURE_VOCAB_SIZE: "
            f"{value} >= {POSITION_FEATURE_VOCAB_SIZE}"
        )
    return value


def _set_feature(
    features: list[tuple[int, int]],
    index: int,
    *,
    feature_index: int,
    value: int,
) -> None:
    current = list(features[index])
    current[feature_index] = value
    features[index] = (current[0], current[1])


def _majority_feature(values) -> int:
    non_none = [value for value in values if value != FEATURE_NONE_ID]
    if not non_none:
        return FEATURE_NONE_ID
    return Counter(non_none).most_common(1)[0][0]
