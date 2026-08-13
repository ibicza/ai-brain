from __future__ import annotations

from typing import Any

from ai_brain.language.tokenizer.special_tokens import (
    ANSWER_TOKEN,
    END_TOKEN,
    PROMPT_TOKEN,
)


def format_prompt_answer(prompt: str, answer: str) -> str:
    return f"{PROMPT_TOKEN}\n{prompt.strip()}\n{ANSWER_TOKEN}\n{answer.strip()}\n{END_TOKEN}"


def format_training_example(example: dict[str, Any]) -> str:
    return format_prompt_answer(
        prompt=str(example["prompt"]),
        answer=str(example["answer"]),
    )
