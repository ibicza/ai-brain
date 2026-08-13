from __future__ import annotations

import re

from ai_brain.eval.normalize import normalize_answer
from ai_brain.language.tokenizer.special_tokens import END_TOKEN, EOS_TOKEN

_MARKER_RE = re.compile(
    r"(?im)^\s*(?:answer|out|final)\s*(?::|=)?\s*(?P<answer>.+?)\s*$"
)
_DIGIT_SPACED_NUMBER_RE = re.compile(r"^[+-]?\d(?:\s+\d)+$")
_PLAIN_NUMBER_RE = re.compile(r"^[+-]?\d+$")


def extract_final_answer(text: str) -> str:
    clean_text = _before_special_token(text)
    matches = list(_MARKER_RE.finditer(clean_text))
    if not matches:
        return clean_text.strip()

    return matches[-1].group("answer").strip()


def normalize_final_answer(answer: str) -> str:
    normalized = normalize_answer(answer)
    if _is_digit_spaced_single_number(normalized):
        return normalized.replace(" ", "")
    return normalized


def final_answers_match(expected: str, predicted: str) -> bool:
    expected_final = extract_final_answer(expected)
    predicted_final = extract_final_answer(predicted)
    return normalize_final_answer(expected_final) == normalize_final_answer(
        predicted_final
    )


def _before_special_token(text: str) -> str:
    positions = [
        position
        for token in (END_TOKEN, EOS_TOKEN)
        if (position := text.find(token)) != -1
    ]
    if not positions:
        return text
    return text[: min(positions)]


def _is_digit_spaced_single_number(answer: str) -> bool:
    if "," in answer or "|" in answer:
        return False
    return bool(_DIGIT_SPACED_NUMBER_RE.fullmatch(answer))


def is_single_plain_number(answer: str) -> bool:
    return bool(_PLAIN_NUMBER_RE.fullmatch(normalize_answer(answer)))
