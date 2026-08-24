"""Measured tokenizer audit for controlled Russian and English commands."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from statistics import mean
from typing import Any

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer

IMPORTANT_VOCABULARY = {
    "ru": (
        "перемести",
        "перенеси",
        "удали",
        "очисти",
        "оставь",
        "сохрани",
        "не изменяй",
        "заверши",
        "опустеет",
        "все элементы",
        "по очереди",
    ),
    "en": (
        "move",
        "transfer",
        "drop",
        "remove",
        "clear",
        "preserve",
        "leave unchanged",
        "stop",
        "empty",
        "all items",
        "then",
    ),
}


def audit_tokenizer(
    tokenizer_path: Path,
    rows: Sequence[dict[str, Any]],
    *,
    sample_limit_per_language: int = 2_000,
) -> dict[str, Any]:
    tokenizer = ByteLevelBpeTokenizer.load(tokenizer_path)
    by_language: dict[str, list[dict[str, Any]]] = {"ru": [], "en": []}
    for row in rows:
        language = row["language"]
        if len(by_language[language]) < sample_limit_per_language:
            by_language[language].append(row)
    sentence_metrics = {}
    for language, selected in by_language.items():
        token_counts = [len(tokenizer.encode(row["text"])) for row in selected]
        char_counts = [len(row["text"]) for row in selected]
        sentence_metrics[language] = {
            "count": len(selected),
            "avg_tokens_per_sentence": mean(token_counts),
            "avg_characters_per_sentence": mean(char_counts),
            "tokens_per_character": sum(token_counts) / max(1, sum(char_counts)),
        }
    vocabulary = {}
    for language, phrases in IMPORTANT_VOCABULARY.items():
        vocabulary[language] = {
            phrase: {
                "token_count": len(ids := tokenizer.encode(phrase)),
                "tokens": [tokenizer.id_to_token(value) for value in ids],
            }
            for phrase in phrases
        }
    register_references = {
        language: {
            phrase: len(tokenizer.encode(phrase))
            for phrase in (
                ("A", "register A", "A and B", "from A into C")
                if language == "en"
                else ("A", "регистр A", "A и B", "из A в C")
            )
        }
        for language in ("ru", "en")
    }
    cyrillic_characters = 0
    cyrillic_byte_piece_characters = 0
    for row in by_language["ru"]:
        encoded = tokenizer.encode_with_offsets(row["text"])
        for index, character in enumerate(row["text"]):
            if not ("А" <= character <= "я" or character in "Ёё"):
                continue
            cyrillic_characters += 1
            pieces = sum(start <= index < end for start, end in encoded.offsets)
            if pieces > 1:
                cyrillic_byte_piece_characters += 1
    ru_avg = sentence_metrics["ru"]["avg_tokens_per_sentence"]
    en_avg = sentence_metrics["en"]["avg_tokens_per_sentence"]
    return {
        "tokenizer_path": str(tokenizer_path),
        "tokenizer": tokenizer.info(),
        "sentence_metrics": sentence_metrics,
        "ru_en_token_length_ratio": ru_avg / max(en_avg, 1e-9),
        "cyrillic_character_count": cyrillic_characters,
        "cyrillic_characters_split_into_multiple_byte_pieces": cyrillic_byte_piece_characters,
        "cyrillic_byte_piece_fraction": cyrillic_byte_piece_characters
        / max(1, cyrillic_characters),
        "register_references": register_references,
        "important_vocabulary": vocabulary,
    }


def compare_tokenizer_audits(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    result = {}
    for language in ("ru", "en"):
        old = baseline["sentence_metrics"][language]["avg_tokens_per_sentence"]
        new = candidate["sentence_metrics"][language]["avg_tokens_per_sentence"]
        result[language] = {
            "baseline_avg_tokens": old,
            "candidate_avg_tokens": new,
            "token_reduction_fraction": (old - new) / max(old, 1e-9),
        }
    result["retraining_justified"] = any(
        row["token_reduction_fraction"] >= 0.20 for row in result.values()
    )
    return result


def write_tokenizer_audit(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
