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
    random_position_offset,
)
from ai_brain.segments import (
    SEG_ANSWER,
    SEG_CONTEXT,
    SEG_CONTROL,
    SEG_PAD,
    SEG_QUERY,
    SEGMENT_IDS,
)
from ai_brain.training.config import LossMode

IGNORE_INDEX = -100
CACHE_FORMAT_VERSION = 8
RELEVANCE_IGNORE_INDEX = -100


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
    relevance_labels: list[int]
    segment_ids: list[int]
    context_access_mask: list[int]
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
        relevance_labels: torch.Tensor | None = None,
        segment_ids: torch.Tensor | None = None,
        context_access_mask: torch.Tensor | None = None,
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
        self.relevance_labels = _relevance_tensor_or_ignore(
            relevance_labels,
            input_ids,
        )
        self.segment_ids = _segment_tensor_or_default(segment_ids, input_ids)
        self.context_access_mask = _context_access_tensor_or_zeros(
            context_access_mask,
            input_ids,
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
            "relevance_labels": self.relevance_labels[index],
            "segment_ids": self.segment_ids[index],
            "context_access_mask": self.context_access_mask[index],
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
    coupled_position_offset: int = 0,
    active_prompt_start_char: int | None = None,
    segment_spans: list[dict[str, Any]] | None = None,
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
    prefix_encoded = tokenizer.encode_with_offsets(
        prefix_text,
        numeric_tokenization=numeric_tokenization,
    )
    if prefix_encoded.ids != prefix_token_ids:
        raise ValueError("numeric feature and relevance tokenization mismatch")
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
        coupled_offset=coupled_position_offset,
    )
    answer_position_ids, answer_position_features = encode_text_position_features(
        answer_text,
        tokenizer,
        numeric_tokenization=numeric_tokenization,
        abacus_offset=abacus_position_offset,
        coupled_offset=coupled_position_offset,
    )
    if (
        prefix_position_ids != prefix_token_ids
        or answer_position_ids != answer_token_ids
    ):
        raise ValueError("numeric feature and position feature tokenization mismatch")
    prefix_ids = [bos_id, *prefix_token_ids]
    answer_ids = [*answer_token_ids, eos_id]
    ids = [*prefix_ids, *answer_ids]
    relevance_labels = _build_relevance_labels(
        prompt=prompt.strip(),
        prefix_text=prefix_text,
        prefix_offsets=prefix_encoded.offsets,
        prefix_ids=prefix_ids,
        answer_ids=answer_ids,
        active_prompt_start_char=active_prompt_start_char,
    )
    segment_ids, context_access_mask = _build_segment_arrays(
        prompt=prompt.strip(),
        prefix_text=prefix_text,
        prefix_offsets=prefix_encoded.offsets,
        prefix_ids=prefix_ids,
        answer_ids=answer_ids,
        active_prompt_start_char=active_prompt_start_char,
        segment_spans=segment_spans,
    )
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
        relevance_labels = relevance_labels[:sequence_length]
        segment_ids = segment_ids[:sequence_length]
        context_access_mask = context_access_mask[:sequence_length]

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
        relevance_labels.extend([RELEVANCE_IGNORE_INDEX] * pad_count)
        segment_ids.extend([SEG_PAD] * pad_count)
        context_access_mask.extend([0] * pad_count)

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
        relevance_labels=relevance_labels,
        segment_ids=segment_ids,
        context_access_mask=context_access_mask,
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
    coupled_random_offset_max: int = 0,
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
        coupled_random_offset_max=coupled_random_offset_max,
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
            coupled_position_offset=random_position_offset(
                max_offset=coupled_random_offset_max,
                seed=position_offset_seed,
                index=index,
            ),
            active_prompt_start_char=_active_prompt_start_char(record),
            segment_spans=_segment_spans(record),
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
    relevance_labels = torch.tensor(
        [example.relevance_labels for example in examples],
        dtype=torch.long,
    )
    segment_ids = torch.tensor(
        [example.segment_ids for example in examples],
        dtype=torch.long,
    )
    context_access_mask = torch.tensor(
        [example.context_access_mask for example in examples],
        dtype=torch.long,
    )

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
        "relevance_labels": relevance_labels,
        "segment_ids": segment_ids,
        "context_access_mask": context_access_mask,
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
        relevance_labels=payload.get("relevance_labels"),
        segment_ids=payload.get("segment_ids"),
        context_access_mask=payload.get("context_access_mask"),
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
    coupled_random_offset_max: int = 0,
    position_offset_seed: int = 0,
) -> Path:
    loss_name = loss_mode.replace("-", "_")
    tokenization_name = numeric_tokenization.replace("-", "_")
    offset_name = (
        f"abacus{abacus_random_offset_max}_coupled{coupled_random_offset_max}"
        f"_seed{position_offset_seed}"
    )
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


def _relevance_tensor_or_ignore(
    relevance_labels: torch.Tensor | None,
    input_ids: torch.Tensor,
) -> torch.Tensor:
    if relevance_labels is None:
        return torch.full_like(input_ids, RELEVANCE_IGNORE_INDEX, dtype=torch.long)
    if relevance_labels.shape != input_ids.shape:
        raise ValueError("relevance_labels tensor must match input_ids shape")
    return relevance_labels.long()


def _segment_tensor_or_default(
    segment_ids: torch.Tensor | None,
    input_ids: torch.Tensor,
) -> torch.Tensor:
    if segment_ids is None:
        result = torch.full_like(input_ids, SEG_QUERY, dtype=torch.long)
        result[input_ids == 0] = SEG_PAD
        return result
    if segment_ids.shape != input_ids.shape:
        raise ValueError("segment_ids tensor must match input_ids shape")
    return segment_ids.long()


def _context_access_tensor_or_zeros(
    context_access_mask: torch.Tensor | None,
    input_ids: torch.Tensor,
) -> torch.Tensor:
    if context_access_mask is None:
        return torch.zeros_like(input_ids, dtype=torch.long)
    if context_access_mask.shape != input_ids.shape:
        raise ValueError("context_access_mask tensor must match input_ids shape")
    return context_access_mask.long()


def _build_relevance_labels(
    *,
    prompt: str,
    prefix_text: str,
    prefix_offsets: list[tuple[int, int]],
    prefix_ids: list[int],
    answer_ids: list[int],
    active_prompt_start_char: int | None,
) -> list[int]:
    labels = [RELEVANCE_IGNORE_INDEX]
    if active_prompt_start_char is None:
        labels.extend([RELEVANCE_IGNORE_INDEX] * (len(prefix_ids) - 1))
    else:
        prompt_start = len(f"{PROMPT_TOKEN}\n")
        prompt_end = prompt_start + len(prompt)
        active_start = prompt_start + active_prompt_start_char
        for start, end in prefix_offsets:
            if start >= prompt_end or end <= prompt_start:
                labels.append(RELEVANCE_IGNORE_INDEX)
            elif end <= active_start:
                labels.append(0)
            else:
                labels.append(1)
    labels.extend([RELEVANCE_IGNORE_INDEX] * len(answer_ids))
    return labels


def _build_segment_arrays(
    *,
    prompt: str,
    prefix_text: str,
    prefix_offsets: list[tuple[int, int]],
    prefix_ids: list[int],
    answer_ids: list[int],
    active_prompt_start_char: int | None,
    segment_spans: list[dict[str, Any]] | None,
) -> tuple[list[int], list[int]]:
    segment_ids = [SEG_CONTROL]
    access_mask = [0]
    prompt_start = len(f"{PROMPT_TOKEN}\n")
    prompt_end = prompt_start + len(prompt)
    normalized_spans = _normalize_segment_spans(segment_spans)
    active_start = (
        prompt_start + active_prompt_start_char
        if active_prompt_start_char is not None
        else None
    )

    for start, end in prefix_offsets:
        if start >= prompt_end or end <= prompt_start:
            segment_ids.append(SEG_ANSWER if start >= prompt_end else SEG_CONTROL)
            access_mask.append(0)
            continue
        prompt_relative_start = max(0, start - prompt_start)
        prompt_relative_end = min(len(prompt), end - prompt_start)
        span = _matching_segment_span(
            normalized_spans,
            prompt_relative_start,
            prompt_relative_end,
        )
        if span is not None:
            segment_ids.append(span["segment_id"])
            access_mask.append(int(span["access"]))
        elif active_start is not None and end <= active_start:
            segment_ids.append(SEG_CONTEXT)
            access_mask.append(0)
        else:
            segment_ids.append(SEG_QUERY)
            access_mask.append(0)

    segment_ids.extend([SEG_ANSWER] * len(answer_ids))
    access_mask.extend([0] * len(answer_ids))
    if len(segment_ids) != len(prefix_ids) + len(answer_ids):
        raise ValueError("segment id tokenization mismatch")
    return segment_ids, access_mask


def _normalize_segment_spans(
    segment_spans: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not segment_spans:
        return []
    normalized = []
    for span in segment_spans:
        name = str(span["segment"])
        if name not in SEGMENT_IDS:
            raise ValueError(f"Unknown segment name in metadata: {name}")
        normalized.append(
            {
                "start": int(span["start"]),
                "end": int(span["end"]),
                "segment_id": SEGMENT_IDS[name],
                "access": bool(span.get("access", False)),
            }
        )
    return normalized


def _matching_segment_span(
    spans: list[dict[str, Any]],
    start: int,
    end: int,
) -> dict[str, Any] | None:
    best = None
    best_overlap = 0
    for span in spans:
        overlap = min(end, span["end"]) - max(start, span["start"])
        if overlap > best_overlap:
            best = span
            best_overlap = overlap
    return best


def _active_prompt_start_char(record: dict[str, Any]) -> int | None:
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("active_prompt_start_char")
    if value is None:
        return None
    return int(value)


def _segment_spans(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("segment_spans")
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError("metadata.segment_spans must be a list")
    return value


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
    coupled_random_offset_max: int,
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
        "coupled_random_offset_max": coupled_random_offset_max,
        "position_offset_seed": position_offset_seed,
    }


def _cache_metadata_matches(
    cached: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    return all(cached.get(key) == value for key, value in expected.items())
