from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import (
    ANSWER_TOKEN,
    BOS_TOKEN,
    EOS_TOKEN,
    PAD_TOKEN,
)
from ai_brain.language.tokenizer.text_format import format_prompt_answer
from ai_brain.training.config import LossMode

IGNORE_INDEX = -100


@dataclass(frozen=True)
class EncodedLmExample:
    input_ids: list[int]
    labels: list[int]
    attention_mask: list[int]


class TokenizedLmDataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(
        self,
        *,
        input_ids: torch.Tensor,
        labels: torch.Tensor,
        attention_mask: torch.Tensor,
        metadata: dict[str, Any],
    ) -> None:
        if input_ids.shape != labels.shape or input_ids.shape != attention_mask.shape:
            raise ValueError(
                "input_ids, labels, and attention_mask must have same shape"
            )
        if input_ids.ndim != 2:
            raise ValueError("dataset tensors must have shape [count, sequence_length]")

        self.input_ids = input_ids.long()
        self.labels = labels.long()
        self.attention_mask = attention_mask.long()
        self.metadata = metadata

    def __len__(self) -> int:
        return int(self.input_ids.shape[0])

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return {
            "input_ids": self.input_ids[index],
            "labels": self.labels[index],
            "attention_mask": self.attention_mask[index],
        }


def encode_lm_example(
    *,
    prompt: str,
    answer: str,
    tokenizer: ByteLevelBpeTokenizer,
    sequence_length: int,
    loss_mode: LossMode,
) -> EncodedLmExample:
    if sequence_length < 2:
        raise ValueError("sequence_length must be at least 2")

    pad_id = _required_token_id(tokenizer, PAD_TOKEN)
    bos_id = _required_token_id(tokenizer, BOS_TOKEN)
    eos_id = _required_token_id(tokenizer, EOS_TOKEN)
    answer_id = _required_token_id(tokenizer, ANSWER_TOKEN)

    encoded_text = tokenizer.encode(format_prompt_answer(prompt, answer))
    ids = [bos_id, *encoded_text, eos_id]
    ids = ids[:sequence_length]
    if ids[-1] != eos_id and len(ids) == sequence_length:
        ids[-1] = eos_id

    labels = list(ids)
    if loss_mode == "answer-only":
        try:
            answer_index = ids.index(answer_id)
        except ValueError:
            answer_index = len(ids)
        labels[:answer_index] = [IGNORE_INDEX] * answer_index
    elif loss_mode != "full":
        raise ValueError(f"Unknown loss_mode: {loss_mode}")

    attention_mask = [1] * len(ids)

    pad_count = sequence_length - len(ids)
    if pad_count > 0:
        ids.extend([pad_id] * pad_count)
        labels.extend([IGNORE_INDEX] * pad_count)
        attention_mask.extend([0] * pad_count)

    return EncodedLmExample(
        input_ids=ids,
        labels=labels,
        attention_mask=attention_mask,
    )


def prepare_lm_dataset(
    *,
    input_path: Path,
    tokenizer_path: Path,
    output_path: Path,
    sequence_length: int,
    loss_mode: LossMode = "answer-only",
    force: bool = False,
) -> dict[str, Any]:
    expected_metadata = _build_metadata(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        sequence_length=sequence_length,
        loss_mode=loss_mode,
    )

    if output_path.exists() and not force:
        cached = torch.load(output_path, map_location="cpu")
        metadata = dict(cached.get("metadata", {}))
        if _cache_metadata_matches(metadata, expected_metadata):
            return {
                "cache_path": str(output_path),
                "count": int(cached["input_ids"].shape[0]),
                "reused": True,
                "metadata": metadata,
            }

    tokenizer = ByteLevelBpeTokenizer.load(tokenizer_path)
    examples = [
        encode_lm_example(
            prompt=record["prompt"],
            answer=record["answer"],
            tokenizer=tokenizer,
            sequence_length=sequence_length,
            loss_mode=loss_mode,
        )
        for record in _iter_jsonl_records(input_path)
    ]
    if not examples:
        raise ValueError(f"No examples found in {input_path}")

    input_ids = torch.tensor(
        [example.input_ids for example in examples], dtype=torch.long
    )
    labels = torch.tensor([example.labels for example in examples], dtype=torch.long)
    attention_mask = torch.tensor(
        [example.attention_mask for example in examples],
        dtype=torch.long,
    )

    metadata = {
        **expected_metadata,
        "count": len(examples),
        "tokenizer_vocab_size": tokenizer.vocab_size,
    }
    payload = {
        "input_ids": input_ids,
        "labels": labels,
        "attention_mask": attention_mask,
        "metadata": metadata,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, output_path)

    return {
        "cache_path": str(output_path),
        "count": len(examples),
        "reused": False,
        "metadata": metadata,
    }


def load_tokenized_lm_dataset(cache_path: Path) -> TokenizedLmDataset:
    payload = torch.load(cache_path, map_location="cpu")
    return TokenizedLmDataset(
        input_ids=payload["input_ids"],
        labels=payload["labels"],
        attention_mask=payload["attention_mask"],
        metadata=dict(payload["metadata"]),
    )


def default_lm_cache_path(
    *,
    cache_dir: Path,
    input_path: Path,
    tokenizer_path: Path,
    sequence_length: int,
    loss_mode: LossMode,
) -> Path:
    loss_name = loss_mode.replace("-", "_")
    filename = (
        f"{input_path.stem}_{tokenizer_path.stem}_seq{sequence_length}_{loss_name}.pt"
    )
    return cache_dir / filename


def _required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Tokenizer is missing required special token: {token}")
    return token_id


def _iter_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if "prompt" not in record or "answer" not in record:
                raise ValueError(f"Record is missing prompt/answer in {path}")
            records.append(record)
    return records


def _build_metadata(
    *,
    input_path: Path,
    tokenizer_path: Path,
    sequence_length: int,
    loss_mode: LossMode,
) -> dict[str, Any]:
    source_stat = input_path.stat()
    tokenizer_stat = tokenizer_path.stat()
    return {
        "source": str(input_path),
        "source_size": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
        "tokenizer_path": str(tokenizer_path),
        "tokenizer_size": tokenizer_stat.st_size,
        "tokenizer_mtime_ns": tokenizer_stat.st_mtime_ns,
        "sequence_length": sequence_length,
        "loss_mode": loss_mode,
    }


def _cache_metadata_matches(
    cached: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    return all(cached.get(key) == value for key, value in expected.items())
