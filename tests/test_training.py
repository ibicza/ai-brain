from __future__ import annotations

import json

import torch

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import ANSWER_TOKEN, PAD_TOKEN
from ai_brain.language.tokenizer.text_format import format_prompt_answer
from ai_brain.training.batching import sample_batch
from ai_brain.training.config import TrainConfig
from ai_brain.training.lm_dataset import (
    IGNORE_INDEX,
    TokenizedLmDataset,
    encode_lm_example,
    load_tokenized_lm_dataset,
    prepare_lm_dataset,
)
from ai_brain.training.loop import train_lm


def _records() -> list[dict[str, str]]:
    return [
        {
            "prompt": "Add 2 + 2.",
            "answer": "4",
            "task_type": "arithmetic.add",
        },
        {
            "prompt": "\u0423 \u041c\u0430\u0448\u0438 7 \u044f\u0431\u043b\u043e\u043a. \u0421\u043a\u043e\u043b\u044c\u043a\u043e?",
            "answer": "7",
            "task_type": "quantity.direct",
        },
        {
            "prompt": "Sort 3, 1, 2.",
            "answer": "1, 2, 3",
            "task_type": "sorting.numbers",
        },
    ]


def _write_jsonl(path, records: list[dict[str, str]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )


def _train_tokenizer(
    tmp_path, records: list[dict[str, str]]
) -> tuple[ByteLevelBpeTokenizer, object]:
    tokenizer_path = tmp_path / "tokenizer.json"
    tokenizer = ByteLevelBpeTokenizer.train(
        [
            format_prompt_answer(record["prompt"], record["answer"])
            for record in records
        ],
        vocab_size=512,
        min_frequency=1,
    )
    tokenizer.save(tokenizer_path)
    return tokenizer, tokenizer_path


def test_answer_only_labels_ignore_prompt_tokens(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(tmp_path, _records())
    encoded = encode_lm_example(
        prompt="Add 2 + 2.",
        answer="4",
        tokenizer=tokenizer,
        sequence_length=32,
        loss_mode="answer-only",
    )
    answer_id = tokenizer.token_to_id(ANSWER_TOKEN)
    answer_index = encoded.input_ids.index(answer_id)

    assert encoded.labels[:answer_index] == [IGNORE_INDEX] * answer_index
    assert encoded.labels[answer_index] == answer_id
    assert any(label != IGNORE_INDEX for label in encoded.labels[answer_index:])


def test_full_loss_labels_all_non_padding_tokens(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(tmp_path, _records())
    encoded = encode_lm_example(
        prompt="Add 2 + 2.",
        answer="4",
        tokenizer=tokenizer,
        sequence_length=32,
        loss_mode="full",
    )
    pad_id = tokenizer.token_to_id(PAD_TOKEN)

    for input_id, label, mask in zip(
        encoded.input_ids,
        encoded.labels,
        encoded.attention_mask,
        strict=True,
    ):
        if mask:
            assert label == input_id
        else:
            assert input_id == pad_id
            assert label == IGNORE_INDEX


def test_prepare_lm_dataset_reuses_matching_cache(tmp_path) -> None:
    records = _records()
    input_path = tmp_path / "train.jsonl"
    output_path = tmp_path / "cache.pt"
    _write_jsonl(input_path, records)
    _tokenizer, tokenizer_path = _train_tokenizer(tmp_path, records)

    first = prepare_lm_dataset(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        output_path=output_path,
        sequence_length=32,
        loss_mode="answer-only",
    )
    second = prepare_lm_dataset(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        output_path=output_path,
        sequence_length=32,
        loss_mode="answer-only",
    )

    assert first["reused"] is False
    assert second["reused"] is True
    assert second["metadata"]["loss_mode"] == "answer-only"


def test_prepare_lm_dataset_rebuilds_on_loss_mode_mismatch(tmp_path) -> None:
    records = _records()
    input_path = tmp_path / "train.jsonl"
    output_path = tmp_path / "cache.pt"
    _write_jsonl(input_path, records)
    _tokenizer, tokenizer_path = _train_tokenizer(tmp_path, records)

    prepare_lm_dataset(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        output_path=output_path,
        sequence_length=32,
        loss_mode="answer-only",
    )
    rebuilt = prepare_lm_dataset(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        output_path=output_path,
        sequence_length=32,
        loss_mode="full",
    )

    assert rebuilt["reused"] is False
    assert rebuilt["metadata"]["loss_mode"] == "full"


def test_sample_batch_shapes(tmp_path) -> None:
    records = _records()
    input_path = tmp_path / "train.jsonl"
    output_path = tmp_path / "cache.pt"
    _write_jsonl(input_path, records)
    _tokenizer, tokenizer_path = _train_tokenizer(tmp_path, records)
    prepare_lm_dataset(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        output_path=output_path,
        sequence_length=32,
        loss_mode="answer-only",
    )
    dataset = load_tokenized_lm_dataset(output_path)

    batch = sample_batch(
        dataset,
        batch_size=2,
        device=torch.device("cpu"),
        generator=torch.Generator().manual_seed(1234),
    )

    assert isinstance(dataset, TokenizedLmDataset)
    assert batch["input_ids"].shape == (2, 32)
    assert batch["labels"].shape == (2, 32)
    assert batch["attention_mask"].shape == (2, 32)


def test_train_lm_smoke_writes_metrics_and_checkpoint(tmp_path) -> None:
    records = _records()
    train_path = tmp_path / "train.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "run"
    cache_dir = tmp_path / "tokenized"
    _write_jsonl(train_path, records)
    _write_jsonl(eval_path, records)
    _tokenizer, tokenizer_path = _train_tokenizer(tmp_path, records)

    result = train_lm(
        TrainConfig(
            train_path=train_path,
            eval_path=eval_path,
            tokenizer_path=tokenizer_path,
            output_dir=output_dir,
            model_config_name="debug",
            steps=2,
            batch_size=2,
            sequence_length=32,
            loss_mode="answer-only",
            eval_every=1,
            eval_batches=1,
            save_every=2,
            cache_dir=cache_dir,
            cpu=True,
        )
    )

    metrics_lines = (
        (output_dir / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    )
    checkpoint_path = output_dir / "checkpoints" / "step_000002.pt"
    checkpoint = torch.load(checkpoint_path, map_location="cpu")

    assert result["final_step"] == 2
    assert len(metrics_lines) == 2
    assert checkpoint_path.exists()
    assert checkpoint["step"] == 2
    assert "model_state_dict" in checkpoint
    assert "optimizer_state_dict" in checkpoint
    assert checkpoint["train_config"]["loss_mode"] == "answer-only"
