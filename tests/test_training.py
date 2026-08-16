from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import (
    ANSWER_TOKEN,
    EOS_TOKEN,
    PAD_TOKEN,
)
from ai_brain.language.tokenizer.text_format import format_prompt_answer
from ai_brain.numeric_features import (
    DIGIT_PLACE_IDS,
    NUMBER_ROLE_IDS,
    OPERATION_STEP_IDS,
    encode_text_numeric_features,
)
from ai_brain.numeric_position_features import encode_text_position_features
from ai_brain.segments import SEG_CONTEXT, SEG_PAD, SEG_QUERY
from ai_brain.training.batching import sample_batch
from ai_brain.training.config import TrainConfig
from ai_brain.training.lm_dataset import (
    CACHE_FORMAT_VERSION,
    IGNORE_INDEX,
    TokenizedLmDataset,
    encode_lm_example,
    load_tokenized_lm_dataset,
    prepare_lm_dataset,
)
from ai_brain.training.loop import _sample_position_offset, train_lm


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


def test_answer_only_ignores_answer_marker(tmp_path) -> None:
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

    assert encoded.labels[: answer_index + 1] == [IGNORE_INDEX] * (answer_index + 1)
    assert any(label != IGNORE_INDEX for label in encoded.labels[answer_index + 1 :])


def test_answer_only_first_supervised_token_is_answer_text(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(tmp_path, _records())
    encoded = encode_lm_example(
        prompt="Add 2 + 2.",
        answer="4",
        tokenizer=tokenizer,
        sequence_length=32,
        loss_mode="answer-only",
    )
    first_supervised = next(label for label in encoded.labels if label != IGNORE_INDEX)

    assert tokenizer.decode([first_supervised], skip_special_tokens=False).startswith(
        "4"
    )


def test_encode_lm_example_builds_segment_ids_from_metadata(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "NOISE\nADD 12 + 34",
                "answer": "FINAL 46",
                "task_type": "m18.add",
            }
        ],
    )

    encoded = encode_lm_example(
        prompt="NOISE\nADD 12 + 34",
        answer="FINAL 46",
        tokenizer=tokenizer,
        sequence_length=64,
        loss_mode="answer-only",
        segment_spans=[
            {"segment": "context", "start": 0, "end": 6, "access": False},
            {"segment": "query", "start": 6, "end": 17, "access": False},
        ],
    )

    real_segments = encoded.segment_ids[: sum(encoded.attention_mask)]
    assert SEG_CONTEXT in real_segments
    assert SEG_QUERY in real_segments
    assert encoded.segment_ids[-1] == SEG_PAD


def test_truncated_example_does_not_fake_eos(tmp_path) -> None:
    records = [
        {
            "prompt": "Short prompt.",
            "answer": " ".join(str(index) for index in range(100)),
            "task_type": "long.answer",
        }
    ]
    tokenizer, _tokenizer_path = _train_tokenizer(tmp_path, records)
    encoded = encode_lm_example(
        prompt=records[0]["prompt"],
        answer=records[0]["answer"],
        tokenizer=tokenizer,
        sequence_length=16,
        loss_mode="full",
    )
    eos_id = tokenizer.token_to_id(EOS_TOKEN)
    last_real_index = sum(encoded.attention_mask) - 1

    assert encoded.truncated is True
    assert encoded.input_ids[last_real_index] != eos_id


def test_answer_only_raises_when_no_supervised_tokens(tmp_path) -> None:
    records = [
        {
            "prompt": " ".join(f"word{index}" for index in range(100)),
            "answer": "answer",
            "task_type": "long.prompt",
        }
    ]
    tokenizer, _tokenizer_path = _train_tokenizer(tmp_path, records)

    with pytest.raises(ValueError, match="No supervised tokens after truncation"):
        encode_lm_example(
            prompt=records[0]["prompt"],
            answer=records[0]["answer"],
            tokenizer=tokenizer,
            sequence_length=8,
            loss_mode="answer-only",
        )


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
    assert second["metadata"]["cache_format_version"] == CACHE_FORMAT_VERSION


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


def test_prepare_lm_dataset_reports_truncation_stats(tmp_path) -> None:
    records = [
        {"prompt": "Short.", "answer": "ok", "task_type": "short"},
        {
            "prompt": "Short prompt.",
            "answer": " ".join(str(index) for index in range(100)),
            "task_type": "long.answer",
        },
    ]
    input_path = tmp_path / "train.jsonl"
    output_path = tmp_path / "cache.pt"
    _write_jsonl(input_path, records)
    _tokenizer, tokenizer_path = _train_tokenizer(tmp_path, records)

    result = prepare_lm_dataset(
        input_path=input_path,
        tokenizer_path=tokenizer_path,
        output_path=output_path,
        sequence_length=32,
        loss_mode="answer-only",
    )
    metadata = result["metadata"]

    assert metadata["truncated_count"] == 1
    assert metadata["truncated_fraction"] == 0.5
    assert metadata["zero_supervised_count"] == 0
    assert metadata["min_supervised_token_count"] > 0
    assert (
        metadata["max_supervised_token_count"] >= metadata["min_supervised_token_count"]
    )
    assert metadata["avg_supervised_token_count"] > 0


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


def test_train_lm_can_train_recurrent_debug(tmp_path) -> None:
    records = _records()
    train_path = tmp_path / "train.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "recurrent_run"
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
            model_config_name="recurrent_debug",
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

    checkpoint_path = output_dir / "checkpoints" / "step_000002.pt"
    checkpoint = torch.load(checkpoint_path, map_location="cpu")

    assert result["model_config"]["model_type"] == "recurrent"
    assert checkpoint["model_config"]["model_type"] == "recurrent"
    assert checkpoint["model_config"]["recurrent_cycles"] == 2


def test_train_lm_uses_grad_clip(tmp_path, monkeypatch) -> None:
    records = _records()
    train_path = tmp_path / "train.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "run"
    cache_dir = tmp_path / "tokenized"
    _write_jsonl(train_path, records)
    _write_jsonl(eval_path, records)
    _tokenizer, tokenizer_path = _train_tokenizer(tmp_path, records)
    calls: list[float] = []
    original_clip_grad_norm = torch.nn.utils.clip_grad_norm_

    def recording_clip_grad_norm_(parameters, max_norm, *args, **kwargs):
        calls.append(float(max_norm))
        return original_clip_grad_norm(parameters, max_norm, *args, **kwargs)

    monkeypatch.setattr(torch.nn.utils, "clip_grad_norm_", recording_clip_grad_norm_)

    result = train_lm(
        TrainConfig(
            train_path=train_path,
            eval_path=eval_path,
            tokenizer_path=tokenizer_path,
            output_dir=output_dir,
            model_config_name="debug",
            steps=1,
            batch_size=2,
            sequence_length=32,
            loss_mode="answer-only",
            eval_every=1,
            eval_batches=1,
            save_every=1,
            cache_dir=cache_dir,
            grad_clip_norm=0.5,
            cpu=True,
        )
    )

    metrics = json.loads((output_dir / "metrics.jsonl").read_text(encoding="utf-8"))
    assert calls == [0.5]
    assert "grad_norm" in metrics
    assert result["last_metrics"]["grad_norm"] == metrics["grad_norm"]


def test_randomized_absolute_sampler_preserves_order_with_gaps(tmp_path) -> None:
    config = TrainConfig(
        train_path=tmp_path / "train.jsonl",
        eval_path=tmp_path / "eval.jsonl",
        tokenizer_path=tmp_path / "tokenizer.json",
        output_dir=tmp_path / "run",
        position_encoding="randomized_absolute",
        position_shift_max=16,
        batch_size=4,
        sequence_length=8,
    )
    positions = _sample_position_offset(
        config=config,
        batch_size=4,
        device=torch.device("cpu"),
        generator=torch.Generator().manual_seed(1234),
    )

    assert isinstance(positions, torch.Tensor)
    assert positions.shape == (4, 8)
    assert torch.all(positions[:, 1:] > positions[:, :-1])
    assert (
        int(positions.max().item()) < config.sequence_length + config.position_shift_max
    )
    assert any(
        not torch.equal(row, torch.arange(row[0], row[0] + config.sequence_length))
        for row in positions
    )


def test_train_lm_init_checkpoint_allows_sequence_length_growth(tmp_path) -> None:
    records = _records()
    train_path = tmp_path / "train.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    first_output_dir = tmp_path / "first_run"
    second_output_dir = tmp_path / "second_run"
    cache_dir = tmp_path / "tokenized"
    _write_jsonl(train_path, records)
    _write_jsonl(eval_path, records)
    _tokenizer, tokenizer_path = _train_tokenizer(tmp_path, records)

    first = train_lm(
        TrainConfig(
            train_path=train_path,
            eval_path=eval_path,
            tokenizer_path=tokenizer_path,
            output_dir=first_output_dir,
            model_config_name="debug",
            steps=1,
            batch_size=2,
            sequence_length=32,
            loss_mode="answer-only",
            eval_every=1,
            eval_batches=1,
            save_every=1,
            cache_dir=cache_dir,
            cpu=True,
        )
    )

    second = train_lm(
        TrainConfig(
            train_path=train_path,
            eval_path=eval_path,
            tokenizer_path=tokenizer_path,
            output_dir=second_output_dir,
            model_config_name="debug",
            steps=1,
            batch_size=2,
            sequence_length=40,
            loss_mode="answer-only",
            eval_every=1,
            eval_batches=1,
            save_every=1,
            cache_dir=cache_dir,
            init_checkpoint_path=Path(first["checkpoint_paths"][-1]),
            cpu=True,
        )
    )
    train_config = json.loads(
        (second_output_dir / "train_config.json").read_text(encoding="utf-8")
    )
    initialized = train_config["initialized_from_checkpoint"]

    assert initialized["path"] == first["checkpoint_paths"][-1]
    assert initialized["loaded_key_count"] > 0
    assert initialized["skipped_key_count"] > 0
    assert second["initialized_from_checkpoint"]["skipped_key_count"] > 0


def _feature_rows(text: str, tokenizer: ByteLevelBpeTokenizer):
    ids, features = encode_text_numeric_features(text, tokenizer)
    tokens = [tokenizer.id_to_token(token_id) for token_id in ids]
    return tokens, features


def test_numeric_feature_extraction_on_add_trace(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "case 1. ADD2_COMPOSED 71 + 63",
                "answer": "OP ADD\nA 7 1\nB 6 3\nU 1 3 0 -> 4 0\nT 7 6 0 -> 3 1\nOUT 134",
                "task_type": "arithmetic.add_2digit_composed",
            }
        ],
    )

    _tokens, features = _feature_rows(
        "OP ADD\nA 7 1\nB 6 3\nU 1 3 0 -> 4 0\nT 7 6 0 -> 3 1\nOUT 134",
        tokenizer,
    )

    assert 8 in features.digit_value_ids
    assert DIGIT_PLACE_IDS["tens"] in features.digit_place_ids
    assert DIGIT_PLACE_IDS["ones"] in features.digit_place_ids
    assert NUMBER_ROLE_IDS["a"] in features.number_role_ids
    assert NUMBER_ROLE_IDS["b"] in features.number_role_ids
    assert NUMBER_ROLE_IDS["result"] in features.number_role_ids
    assert NUMBER_ROLE_IDS["carry_out"] in features.number_role_ids
    assert OPERATION_STEP_IDS["unit_step"] in features.operation_step_ids
    assert OPERATION_STEP_IDS["tens_step"] in features.operation_step_ids
    assert OPERATION_STEP_IDS["out"] in features.operation_step_ids


def test_numeric_feature_extraction_on_sub_trace(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "case 1. SUB2_COMPOSED 52 - 18",
                "answer": "OP SUB\nA 5 2\nB 1 8\nU 2 8 0 -> 4 1\nT 5 1 1 -> 3 0\nOUT 34",
                "task_type": "arithmetic.sub_2digit_composed",
            }
        ],
    )

    _tokens, features = _feature_rows(
        "OP SUB\nA 5 2\nB 1 8\nU 2 8 0 -> 4 1\nT 5 1 1 -> 3 0\nOUT 34",
        tokenizer,
    )

    assert NUMBER_ROLE_IDS["borrow_in"] in features.number_role_ids
    assert NUMBER_ROLE_IDS["borrow_out"] in features.number_role_ids
    assert OPERATION_STEP_IDS["unit_step"] in features.operation_step_ids
    assert OPERATION_STEP_IDS["tens_step"] in features.operation_step_ids


def test_encode_lm_example_numeric_feature_lengths_match_input_ids(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "case 1. ADD_DIGIT a=3 b=4 c=0",
                "answer": "S 7 C 0",
                "task_type": "arithmetic.digit_add_no_carry",
            }
        ],
    )

    encoded = encode_lm_example(
        prompt="case 1. ADD_DIGIT a=3 b=4 c=0",
        answer="S 7 C 0",
        tokenizer=tokenizer,
        sequence_length=64,
        loss_mode="answer-only",
    )

    assert len(encoded.input_ids) == 64
    assert len(encoded.digit_value_ids) == len(encoded.input_ids)
    assert len(encoded.digit_place_ids) == len(encoded.input_ids)
    assert len(encoded.number_role_ids) == len(encoded.input_ids)
    assert len(encoded.operation_step_ids) == len(encoded.input_ids)
    assert len(encoded.abacus_position_ids) == len(encoded.input_ids)
    assert len(encoded.coupled_position_ids) == len(encoded.input_ids)
    assert any(value != 0 for value in encoded.digit_value_ids)


def test_old_text_dataset_gets_none_numeric_features(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(tmp_path, _records())
    encoded = encode_lm_example(
        prompt="No numeric structure here.",
        answer="plain text",
        tokenizer=tokenizer,
        sequence_length=32,
        loss_mode="answer-only",
    )

    assert set(encoded.digit_value_ids) == {0}
    assert set(encoded.digit_place_ids) == {0}
    assert set(encoded.number_role_ids) == {0}
    assert set(encoded.operation_step_ids) == {0}


def test_load_tokenized_lm_dataset_backfills_old_cache_features(tmp_path) -> None:
    cache_path = tmp_path / "old_cache.pt"
    input_ids = torch.ones((2, 8), dtype=torch.long)
    torch.save(
        {
            "input_ids": input_ids,
            "labels": input_ids.clone(),
            "attention_mask": input_ids.clone(),
            "metadata": {"cache_format_version": 2},
        },
        cache_path,
    )

    dataset = load_tokenized_lm_dataset(cache_path)

    assert torch.equal(dataset.digit_value_ids, torch.zeros_like(input_ids))
    assert torch.equal(dataset.operation_step_ids, torch.zeros_like(input_ids))
    assert torch.equal(dataset.abacus_position_ids, torch.zeros_like(input_ids))
    assert torch.equal(dataset.coupled_position_ids, torch.zeros_like(input_ids))


def test_digit_safe_tokenization_splits_decimal_spans(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "case 1. ADD2_COMPOSED 73 + 149",
                "answer": "OUT 222",
                "task_type": "arithmetic.add_2digit_composed",
            }
        ],
    )

    default_ids = tokenizer.encode("73 149")
    digit_safe = tokenizer.encode_with_offsets(
        "73 149",
        numeric_tokenization="digit_safe",
    )
    digit_ids = [tokenizer.encode(str(digit))[0] for digit in range(10)]

    assert tokenizer.decode(digit_safe.ids, skip_special_tokens=False) == "73 149"
    assert len(digit_safe.ids) == 6
    assert digit_safe.ids[:2] == [digit_ids[7], digit_ids[3]]
    assert digit_safe.ids[3:] == [digit_ids[1], digit_ids[4], digit_ids[9]]
    assert len(default_ids) <= len(digit_safe.ids)


def test_position_features_align_with_digit_safe_tokens(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "case 1. ADD2_COMPOSED 71 + 63",
                "answer": "OP ADD\nA 7 1\nB 6 3\nU 1 3 0 -> 4 0\nT 7 6 0 -> 3 1\nOUT 134",
                "task_type": "arithmetic.add_2digit_composed",
            }
        ],
    )
    text = "ADD_COMPOSED 71 + 63\nOUT 134"

    ids, features = encode_text_position_features(
        text,
        tokenizer,
        numeric_tokenization="digit_safe",
    )
    pieces = [
        tokenizer.decode([token_id], skip_special_tokens=False) for token_id in ids
    ]
    digit_rows = [
        (piece, abacus, coupled)
        for piece, abacus, coupled in zip(
            pieces,
            features.abacus_position_ids,
            features.coupled_position_ids,
            strict=True,
        )
        if piece.isdigit()
    ]

    assert digit_rows[:4] == [("7", 2, 2), ("1", 1, 1), ("6", 2, 2), ("3", 1, 1)]
    assert digit_rows[-3:] == [("1", 3, 3), ("3", 2, 2), ("4", 1, 1)]


def test_coupled_position_features_handle_partial_generation(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "case 1. ADD2_COMPOSED 71 + 63",
                "answer": "OP ADD\nA 7 1\nB 6 3\nU 1 3 0 -> 4 0\nT 7",
                "task_type": "arithmetic.add_2digit_composed",
            }
        ],
    )
    text = "OP ADD\nA 7 1\nB 6 3\nU 1 3 0 -> 4\nT 7"

    _ids, features = encode_text_position_features(
        text,
        tokenizer,
        numeric_tokenization="digit_safe",
    )

    nonzero = [value for value in features.coupled_position_ids if value != 0]
    assert nonzero
    assert max(nonzero) <= 2


def test_official_position_coupling_addition_features(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "ADD_PC 84 + 65",
                "answer": "= 9 4 1\nFINAL 149",
                "task_type": "arithmetic.add_balanced",
            }
        ],
    )
    text = "ADD_PC 84 + 65\n= 9 4 1"

    ids, features = encode_text_position_features(
        text,
        tokenizer,
        numeric_tokenization="digit_safe",
    )
    pieces = [
        tokenizer.decode([token_id], skip_special_tokens=False) for token_id in ids
    ]
    marked = [
        (piece.strip(), position)
        for piece, position in zip(
            pieces,
            features.coupled_position_ids,
            strict=True,
        )
        if position != 0
    ]

    assert marked == [
        ("8", 3),
        ("4", 2),
        ("+", 1),
        ("6", 3),
        ("5", 2),
        ("=", 1),
        ("9", 2),
        ("4", 3),
        ("1", 4),
    ]


def test_official_abacus_addition_features_use_reversed_spans(tmp_path) -> None:
    tokenizer, _tokenizer_path = _train_tokenizer(
        tmp_path,
        [
            {
                "prompt": "ADD_ABACUS 48 + 56",
                "answer": "= 941\nFINAL 149",
                "task_type": "arithmetic.add_balanced",
            }
        ],
    )
    text = "ADD_ABACUS 48 + 56\n= 941"

    ids, features = encode_text_position_features(
        text,
        tokenizer,
        numeric_tokenization="digit_safe",
    )
    pieces = [
        tokenizer.decode([token_id], skip_special_tokens=False) for token_id in ids
    ]
    marked_digits = [
        (piece, position)
        for piece, position in zip(
            pieces,
            features.abacus_position_ids,
            strict=True,
        )
        if piece.isdigit()
    ]

    assert marked_digits == [
        ("4", 1),
        ("8", 2),
        ("5", 1),
        ("6", 2),
        ("9", 1),
        ("4", 2),
        ("1", 3),
    ]


def test_train_lm_can_train_abacus_debug_digit_safe(tmp_path) -> None:
    records = [
        {
            "prompt": "case 1. ADD_DIGIT a=3 b=4 c=0",
            "answer": "S 7 C 0",
            "task_type": "arithmetic.digit_add_no_carry",
        },
        {
            "prompt": "case 2. SUB_DIGIT a=8 b=3 borrow=0",
            "answer": "S 5 B 0",
            "task_type": "arithmetic.digit_sub_no_borrow",
        },
    ]
    train_path = tmp_path / "train.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "abacus_run"
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
            model_config_name="abacus_debug",
            steps=1,
            batch_size=2,
            sequence_length=64,
            loss_mode="answer-only",
            numeric_tokenization="digit_safe",
            abacus_random_offset_max=3,
            eval_every=1,
            eval_batches=1,
            save_every=1,
            cache_dir=cache_dir,
            cpu=True,
        )
    )

    assert result["model_config"]["model_type"] == "abacus"
    assert result["train_cache"]["metadata"]["numeric_tokenization"] == "digit_safe"
    assert result["train_cache"]["metadata"]["abacus_random_offset_max"] == 3


def test_train_lm_can_train_numeric_debug(tmp_path) -> None:
    records = [
        {
            "prompt": "case 1. ADD_DIGIT a=3 b=4 c=0",
            "answer": "S 7 C 0",
            "task_type": "arithmetic.digit_add_no_carry",
        },
        {
            "prompt": "case 2. SUB_DIGIT a=8 b=3 borrow=0",
            "answer": "S 5 B 0",
            "task_type": "arithmetic.digit_sub_no_borrow",
        },
    ]
    train_path = tmp_path / "train.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "numeric_run"
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
            model_config_name="numeric_debug",
            steps=1,
            batch_size=2,
            sequence_length=64,
            loss_mode="answer-only",
            eval_every=1,
            eval_batches=1,
            save_every=1,
            cache_dir=cache_dir,
            cpu=True,
        )
    )

    assert result["model_config"]["model_type"] == "numeric"
    assert result["checkpoint_paths"]
