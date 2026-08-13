from __future__ import annotations

import re

from ai_brain.language.tokenizer.special_tokens import (
    ANSWER_TOKEN,
    END_TOKEN,
    EOS_TOKEN,
)

_UNCERTAINTY_MARKERS = (
    "недостаточно",
    "неизвест",
    "нельзя определить",
    "невозможно определить",
    "противореч",
    "ложная предпосылка",
    "insufficient",
    "unknown",
    "cannot determine",
    "contradict",
    "false presupposition",
)


def normalize_answer(answer: str) -> str:
    normalized = answer.strip().lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized.endswith(".") and normalized.count(".") == 1:
        normalized = normalized[:-1].rstrip()
    return normalized


def extract_generated_answer(decoded_text: str) -> str:
    text = decoded_text
    if ANSWER_TOKEN in text:
        text = text.split(ANSWER_TOKEN, 1)[1]

    end_positions = [
        position
        for token in (END_TOKEN, EOS_TOKEN)
        if (position := text.find(token)) != -1
    ]
    if end_positions:
        text = text[: min(end_positions)]

    return text.strip()


def is_epistemic_task(task_type: str) -> bool:
    if task_type.startswith("epistemic."):
        return True
    markers = (
        "insufficient",
        "unknown",
        "contradiction",
        "false_presupposition",
        "false-presupposition",
    )
    return any(marker in task_type for marker in markers)


def is_false_answer(*, task_type: str, expected: str, predicted: str) -> bool:
    if not is_epistemic_task(task_type):
        return False
    if normalize_answer(expected) == normalize_answer(predicted):
        return False

    normalized = normalize_answer(predicted)
    if not normalized:
        return False
    if any(marker in normalized for marker in _UNCERTAINTY_MARKERS):
        return False

    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", normalized):
        return True
    if normalized in {"да", "нет", "yes", "no", "true", "false"}:
        return True
    return len(normalized.split()) <= 3
