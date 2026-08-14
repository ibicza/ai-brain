from __future__ import annotations

import re

from ai_brain.eval.normalize import normalize_answer
from ai_brain.language.tokenizer.special_tokens import END_TOKEN, EOS_TOKEN

_MARKER_RE = re.compile(
    r"(?im)^\s*(?:answer|out|final)\b\s*(?::|=)?\s*(?P<answer>.+?)\s*$"
)
_DIGIT_SPACED_NUMBER_RE = re.compile(r"^[+-]?\d(?:\s+\d)+$")
_ROLE_TAGGED_NUMBER_RE = re.compile(
    r"^(?:out_[a-z0-9]+\s+\d)(?:\s+out_[a-z0-9]+\s+\d)*$"
)
_ROLE_TAGGED_LINE_RE = re.compile(
    r"(?im)^\s*(?:out_[a-z0-9]+\s+\d)(?:\s+out_[a-z0-9]+\s+\d)*\s*$"
)
_ROLE_TAGGED_DIGIT_RE = re.compile(r"out_[a-z0-9]+\s+(\d)")
_PLAIN_NUMBER_RE = re.compile(r"^[+-]?\d+$")


def extract_final_answer(text: str) -> str:
    clean_text = _before_special_token(text)
    matches = list(_MARKER_RE.finditer(clean_text))
    role_matches = list(_ROLE_TAGGED_LINE_RE.finditer(clean_text))
    if role_matches and (not matches or role_matches[-1].start() > matches[-1].start()):
        return role_matches[-1].group(0).strip()

    if not matches:
        return clean_text.strip()

    return matches[-1].group("answer").strip()


def normalize_final_answer(answer: str) -> str:
    normalized = normalize_answer(answer)
    if _is_role_tagged_single_number(normalized):
        return "".join(_ROLE_TAGGED_DIGIT_RE.findall(normalized))
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


def _is_role_tagged_single_number(answer: str) -> bool:
    if "," in answer or "|" in answer:
        return False
    return bool(_ROLE_TAGGED_NUMBER_RE.fullmatch(answer))


def is_single_plain_number(answer: str) -> bool:
    return bool(_PLAIN_NUMBER_RE.fullmatch(normalize_answer(answer)))
