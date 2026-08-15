from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from ai_brain.language.tokenizer.bpe_tokenizer import (
    ByteLevelBpeTokenizer,
    NumericTokenizationMode,
)
from ai_brain.language.tokenizer.special_tokens import (
    ANSWER_TOKEN,
    BOS_TOKEN,
    END_TOKEN,
    EOS_TOKEN,
    PAD_TOKEN,
    PROMPT_TOKEN,
)
from ai_brain.numeric_features import (
    NUMERIC_FEATURE_KEYS,
    NumericFeatureArrays,
    encode_text_numeric_features,
)
from ai_brain.numeric_position_features import (
    POSITION_FEATURE_KEYS,
    NumericPositionFeatureArrays,
    encode_text_position_features,
    random_abacus_offset,
)
from ai_brain.training.config import LossMode

IGNORE_INDEX = -100
CACHE_FORMAT_VERSION = 4


@dataclass(frozen=True)
class EncodedLmExample:
    input_ids: list[int]
    labels: list[int]
    attention_mask: list[int]
    digit_value_ids: list[int]
    digit_place_ids: list[int]
    number_role_ids: list[int]
    operation_step_ids: list[int]
    abacus_position_ids: list[int]
    coupled_position_ids: list[int]
    truncated: bool
    supervised_token_count: int


class TokenizedLmDataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(
        self,
        *,
        input_ids: torch.Tensor,
        labels: torch.Tensor,
        attention_mask: torch.Tensor,
        metadata: dict[str, Any],
        digit_value_ids: torch.Tensor | None = None,
        digit_place_ids: torch.Tensor | None = None,
        number_role_ids: torch.Tensor | None = None,
        operation_step_ids: torch.Tensor | None = None,
        abacus_position_ids: torch.Tensor | None = None,
        coupled_position_ids: torch.Tensor | None = None,
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
        self.digit_value_ids = _feature_tensor_or_zeros(digit_value_ids, input_ids)
        self.digit_place_ids = _feature_tensor_or_zeros(digit_place_ids, input_ids)
        self.number_role_ids = _feature_tensor_or_zeros(number_role_ids, input_ids)
        self.operation_step_ids = _feature_tensor_or_zeros(
            operation_step_ids, input_ids
        )
        self.abacus_position_ids = _feature_tensor_or_zeros(
            abacus_position_ids, input_ids
        )
        self.coupled_position_ids = _feature_tensor_or_zeros(
            coupled_position_ids, input_ids
        )
        self.metadata = metadata

    def __len__(self) -> int:
        return int(self.input_ids.shape[0])

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return {
            "input_ids": self.input_ids[index],
            "labels": self.labels[index],
            "attention_mask": self.attention_mask[index],
            "digit_value_ids": self.digit_value_ids[index],
            "digit_place_ids": self.digit_place_ids[index],
            "number_role_ids": self.number_role_ids[index],
            "operation_step_ids": self.operation_step_ids[index],
            "abacus_position_ids": self.abacus_position_ids[index],
            "coupled_position_ids": self.coupled_position_ids[index],
        }


def encode_lm_example(
    *,
    prompt: str,
    answer: str,
    tokenizer: ByteLevelBpeTokenizer,
    sequence_length: int,
    loss_mode: LossMode,
    numeric_tokenization: NumericTokenizationMode = "default_bpe",
    abacus_position_offset: int = 0,
) -> EncodedLmExample:
    if sequence_length < 2:
        raise ValueError("sequence_length must be at least 2")

    pad_id = _required_token_id(tokenizer, PAD_TOKEN)
    bos_id = _required_token_id(tokenizer, BOS_TOKEN)
    eos_id = _required_token_id(tokenizer, EOS_TOKEN)

    prefix_text = f"{PROMPT_TOKEN}\n{prompt.strip()}\n{ANSWER_TOKEN}\n"
    answer_text = f"{answer.strip()}\n{END_TOKEN}"

    prefix_token_ids, prefix_features = encode_text_numeric_features(
        prefix_text,
        tokenizer,
        numeric_tokenization=numeric_tokenization,
    )
    answer_token_ids, answer_features = encode_text_numeric_features(
        answer_text,
        tokenizer,
        numeric_tokenization=numeric_tokenization,
    )
    prefix_position_ids, prefix_position_features = encode_text_position_features(
        prefix_text,
        tokenizer,
        numeric_tokenization=numeric_tokenization,
        abacus_offset=abacus_position_offset,
    )
    answer_position_ids, answer_position_features = encode_text_position_features(
        answer_text,
        tokenizer,
        numeric_tokenization=numeric_tokenization,
        abacus_offset=abacus_position_offset,
    )
    if (
        prefix_position_ids != prefix_token_ids
        or answer_position_ids != answer_token_ids
    ):
        raise ValueError("numeric feature and position feature tokenization mismatch")
    prefix_ids = [bos_id, *prefix_token_ids]
    answer_ids = [*answer_token_ids, eos_id]
    ids = [*prefix_ids, *answer_ids]
    feature_arrays = NumericFeatureArrays(
        digit_value_ids=[
            0,
            *prefix_features.digit_value_ids,
            *answer_features.digit_value_ids,
            0,
        ],
        digit_place_ids=[
            0,
            *prefix_features.digit_place_ids,
            *answer_features.digit_place_ids,
            0,
        ],
        number_role_ids=[
            0,
            *prefix_features.number_role_ids,
            *answer_features.number_role_ids,
            0,
        ],
        operation_step_ids=[
            0,
            *prefix_features.operation_step_ids,
            *answer_features.operation_step_ids,
            0,
        ],
    )
    position_feature_arrays = NumericPositionFeatureArrays(
        abacus_position_ids=[
            0,
            *prefix_position_features.abacus_position_ids,
            *answer_position_features.abacus_position_ids,
            0,
        ],
        coupled_position_ids=[
            0,
            *prefix_position_features.coupled_position_ids,
            *answer_position_features.coupled_position_ids,
            0,
        ],
    )

    if loss_mode == "answer-only":
        labels = [IGNORE_INDEX] * len(prefix_ids) + answer_ids
    elif loss_mode == "full":
        labels = list(ids)
    else:
        raise ValueError(f"Unknown loss_mode: {loss_mode}")

    truncated = len(ids) > sequence_length
    if truncated:
        ids = ids[:sequence_length]
        labels = labels[:sequence_length]
        feature_arrays = NumericFeatureArrays(
            digit_value_ids=feature_arrays.digit_value_ids[:sequence_length],
            digit_place_ids=feature_arrays.digit_place_ids[:sequence_length],
            number_role_ids=feature_arrays.number_role_ids[:sequence_length],
            operation_step_ids=feature_arrays.operation_step_ids[:sequence_length],
        )
        position_feature_arrays = NumericPositionFeatureArrays(
            abacus_position_ids=position_feature_arrays.abacus_position_ids[
                :sequence_length
            ],
            coupled_position_ids=position_feature_arrays.coupled_position_ids[
                :sequence_length
            ],
        )

    supervised_token_count = sum(label != IGNORE_INDEX for label in labels)
    if loss_mode == "answer-only" and supervised_token_count == 0:
        raise ValueError(
            "No supervised tokens after truncation. "
            "Increase sequence_length or shorten prompts."
        )

    attention_mask = [1] * len(ids)

    pad_count = sequence_length - len(ids)
    if pad_count > 0:
        ids.extend([pad_id] * pad_count)
        labels.extend([IGNORE_INDEX] * pad_count)
        attention_mask.extend([0] * pad_count)
        feature_arrays.digit_value_ids.extend([0] * pad_count)
        feature_arrays.digit_place_ids.extend([0] * pad_count)
        feature_arrays.number_role_ids.extend([0] * pad_count)
        feature_arrays.operation_step_ids.extend([0] * pad_count)
        position_feature_arrays.abacus_position_ids.extend([0] * pad_count)
        position_feature_arrays.coupled_position_ids.extend([0] * pad_count)

    return EncodedLmExample(
        input_ids=ids,
        labels=labels,
        attention_mask=attention_mask,
        digit_value_ids=feature_arrays.digit_value_ids,
        digit_place_ids=feature_arrays.digit_place_ids,
        number_role_ids=feature_arrays.number_role_ids,
        operation_step_ids=feature_arrays.operation_step_ids,
        abacus_position_ids=position_feature_arrays.abacus_position_ids,
        coupled_position_ids=position_feature_arrays.coupled_position_ids,
        truncated=truncated,
        supervised_token_count=supervised_token_count,
    )


def prepare_lm_dataset(
    *,
    input_path: Path,
    tokenizer_path: Path,
    output_path: Path,
    sequence_length: int,
    loss_mode: LossMode = "answer-only",
    numeric_tokenization: NumericTokenizationMode = "default_bpe",
    abacus_random_offset_max: int = 0,
    position_offset_seed: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    expected_metadata = _build_metadata(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        sequence_length=sequence_length,
        loss_mode=loss_mode,
        numeric_tokenization=numeric_tokenization,
        abacus_random_offset_max=abacus_random_offset_max,
        position_offset_seed=position_offset_seed,
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
            numeric_tokenization=numeric_tokenization,
            abacus_position_offset=random_abacus_offset(
                max_offset=abacus_random_offset_max,
                seed=position_offset_seed,
                index=index,
            ),
        )
        for index, record in enumerate(_iter_jsonl_records(input_path))
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
    feature_tensors = {
        key: torch.tensor(
            [getattr(example, key) for example in examples],
            dtype=torch.long,
        )
        for key in (*NUMERIC_FEATURE_KEYS, *POSITION_FEATURE_KEYS)
    }

    stats = _summarize_encoded_examples(examples)
    metadata = {
        **expected_metadata,
        "count": len(examples),
        "tokenizer_vocab_size": tokenizer.vocab_size,
        **stats,
    }
    payload = {
        "input_ids": input_ids,
        "labels": labels,
        "attention_mask": attention_mask,
        **feature_tensors,
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
        digit_value_ids=payload.get("digit_value_ids"),
        digit_place_ids=payload.get("digit_place_ids"),
        number_role_ids=payload.get("number_role_ids"),
        operation_step_ids=payload.get("operation_step_ids"),
        abacus_position_ids=payload.get("abacus_position_ids"),
        coupled_position_ids=payload.get("coupled_position_ids"),
    )


def default_lm_cache_path(
    *,
    cache_dir: Path,
    input_path: Path,
    tokenizer_path: Path,
    sequence_length: int,
    loss_mode: LossMode,
    numeric_tokenization: NumericTokenizationMode = "default_bpe",
    abacus_random_offset_max: int = 0,
    position_offset_seed: int = 0,
) -> Path:
    loss_name = loss_mode.replace("-", "_")
    tokenization_name = numeric_tokenization.replace("-", "_")
    offset_name = f"abacus{abacus_random_offset_max}_seed{position_offset_seed}"
    filename = (
        f"{input_path.stem}_{tokenizer_path.stem}_{tokenization_name}_"
        f"seq{sequence_length}_{loss_name}_{offset_name}.pt"
    )
    return cache_dir / filename


def _feature_tensor_or_zeros(
    feature_tensor: torch.Tensor | None,
    input_ids: torch.Tensor,
) -> torch.Tensor:
    if feature_tensor is None:
        return torch.zeros_like(input_ids, dtype=torch.long)
    if feature_tensor.shape != input_ids.shape:
        raise ValueError("numeric feature tensors must match input_ids shape")
    return feature_tensor.long()


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


def _summarize_encoded_examples(examples: list[EncodedLmExample]) -> dict[str, Any]:
    supervised_counts = [example.supervised_token_count for example in examples]
    truncated_count = sum(example.truncated for example in examples)
    zero_supervised_count = sum(count == 0 for count in supervised_counts)
    return {
        "truncated_count": truncated_count,
        "truncated_fraction": truncated_count / len(examples),
        "min_supervised_token_count": min(supervised_counts),
        "max_supervised_token_count": max(supervised_counts),
        "avg_supervised_token_count": sum(supervised_counts) / len(supervised_counts),
        "zero_supervised_count": zero_supervised_count,
    }


def _build_metadata(
    *,
    input_path: Path,
    tokenizer_path: Path,
    sequence_length: int,
    loss_mode: LossMode,
    numeric_tokenization: NumericTokenizationMode,
    abacus_random_offset_max: int,
    position_offset_seed: int,
) -> dict[str, Any]:
    source_stat = input_path.stat()
    tokenizer_stat = tokenizer_path.stat()
    return {
        "cache_format_version": CACHE_FORMAT_VERSION,
        "source": str(input_path),
        "source_size": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
        "tokenizer_path": str(tokenizer_path),
        "tokenizer_size": tokenizer_stat.st_size,
        "tokenizer_mtime_ns": tokenizer_stat.st_mtime_ns,
        "sequence_length": sequence_length,
        "loss_mode": loss_mode,
        "numeric_tokenization": numeric_tokenization,
        "abacus_random_offset_max": abacus_random_offset_max,
        "position_offset_seed": position_offset_seed,
    }


def _cache_metadata_matches(
    cached: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    return all(cached.get(key) == value for key, value in expected.items())
