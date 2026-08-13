from __future__ import annotations

import json

from ai_brain.cli import main


def test_generate_data_command(tmp_path, capsys) -> None:
    output_path = tmp_path / "smoke.jsonl"

    exit_code = main(
        [
            "generate-data",
            "--output",
            str(output_path),
            "--count",
            "5",
            "--seed",
            "1234",
        ]
    )

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert exit_code == 0
    assert result["count"] == 5
    assert output_path.exists()
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 5


def test_generate_data_command_with_task_type(tmp_path, capsys) -> None:
    output_path = tmp_path / "quantity.jsonl"

    exit_code = main(
        [
            "generate-data",
            "--output",
            str(output_path),
            "--count",
            "5",
            "--seed",
            "1234",
            "--task-type",
            "quantity.direct",
            "--profile",
            "eval",
        ]
    )

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert exit_code == 0
    assert result["count"] == 5
    assert result["profile"] == "eval"
    assert len(lines) == 5

    loaded = [json.loads(line) for line in lines]

    assert {example["task_type"] for example in loaded} == {"quantity.direct"}


def test_generate_data_split_command(tmp_path, capsys) -> None:
    output_dir = tmp_path / "stage1"

    exit_code = main(
        [
            "generate-data-split",
            "--output-dir",
            str(output_dir),
            "--train-count",
            "12",
            "--eval-count",
            "9",
            "--train-seed",
            "1000",
            "--eval-seed",
            "2000",
            "--task-type",
            "arithmetic.add",
            "--task-type",
            "arithmetic.subtract",
            "--task-type",
            "quantity.direct",
        ]
    )

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    manifest = result["manifest"]

    assert exit_code == 0
    assert (output_dir / "train.jsonl").exists()
    assert (output_dir / "eval.jsonl").exists()
    assert (output_dir / "manifest.json").exists()
    assert manifest["splits"]["train"]["count"] == 12
    assert manifest["splits"]["eval"]["count"] == 9
    assert manifest["splits"]["train"]["profile"] == "train"
    assert manifest["splits"]["eval"]["profile"] == "eval"
    assert manifest["splits"]["train"]["duplicate_prompt_count"] == 0
    assert manifest["splits"]["eval"]["duplicate_prompt_count"] == 0
    assert manifest["quality_checks"]["no_prompt_intersection"] is True
    assert manifest["quality_checks"]["all_task_types_present"] is True


def test_dataset_stats_command(tmp_path, capsys) -> None:
    output_path = tmp_path / "add.jsonl"
    main(
        [
            "generate-data",
            "--output",
            str(output_path),
            "--count",
            "5",
            "--seed",
            "1234",
            "--task-type",
            "arithmetic.add",
        ]
    )
    capsys.readouterr()

    exit_code = main(
        [
            "dataset-stats",
            "--input",
            str(output_path),
            "--task-type",
            "arithmetic.add",
            "--top-duplicates",
            "5",
        ]
    )

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert exit_code == 0
    assert result["count"] == 5
    assert result["task_type_counts"] == {"arithmetic.add": 5}
    assert result["all_task_types_present"] is True
    assert result["missing_task_types"] == []
    assert "top_duplicate_prompts" in result


def test_train_tokenizer_and_tokenizer_info_commands(tmp_path, capsys) -> None:
    input_path = tmp_path / "dataset.jsonl"
    output_path = tmp_path / "tokenizer.json"
    input_path.write_text(
        json.dumps(
            {
                "prompt": "Sort 2, 1.",
                "answer": "1, 2",
                "task_type": "sorting.numbers",
            }
        ),
        encoding="utf-8",
    )

    train_exit_code = main(
        [
            "train-tokenizer",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--vocab-size",
            "512",
            "--min-frequency",
            "1",
        ]
    )
    train_output = json.loads(capsys.readouterr().out)

    assert train_exit_code == 0
    assert output_path.exists()
    assert train_output["special_token_ids"]["<|pad|>"] == 0
    assert train_output["special_token_ids"]["<|end|>"] == 6

    info_exit_code = main(["tokenizer-info", "--tokenizer", str(output_path)])
    info_output = json.loads(capsys.readouterr().out)

    assert info_exit_code == 0
    assert info_output["type"] == "byte_level_bpe"
    assert info_output["tokenizer_path"] == str(output_path)
    assert info_output["special_token_ids"] == train_output["special_token_ids"]


def test_encode_text_and_decode_ids_commands(tmp_path, capsys) -> None:
    input_path = tmp_path / "dataset.txt"
    output_path = tmp_path / "tokenizer.json"
    text = "<|prompt|>\nAdd 2 + 2.\n<|answer|>\n4\n<|end|>"
    input_path.write_text(text, encoding="utf-8")
    main(
        [
            "train-tokenizer",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--vocab-size",
            "512",
            "--min-frequency",
            "1",
        ]
    )
    capsys.readouterr()

    encode_exit_code = main(
        ["encode-text", "--tokenizer", str(output_path), "--text", text]
    )
    encoded = json.loads(capsys.readouterr().out)

    assert encode_exit_code == 0
    assert encoded["ids"]
    assert encoded["count"] == len(encoded["ids"])

    ids = ",".join(str(token_id) for token_id in encoded["ids"])
    decode_exit_code = main(
        ["decode-ids", "--tokenizer", str(output_path), "--ids", ids]
    )
    decoded = json.loads(capsys.readouterr().out)

    assert decode_exit_code == 0
    assert decoded["text"] == text
    assert decoded["count"] == len(encoded["ids"])


def test_prepare_lm_dataset_and_train_lm_commands(tmp_path, capsys) -> None:
    train_path = tmp_path / "train.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    tokenizer_path = tmp_path / "tokenizer.json"
    cache_path = tmp_path / "cache.pt"
    output_dir = tmp_path / "run"
    cache_dir = tmp_path / "tokenized"
    records = [
        {"prompt": "Add 2 + 2.", "answer": "4", "task_type": "arithmetic.add"},
        {"prompt": "Sort 2, 1.", "answer": "1, 2", "task_type": "sorting.numbers"},
    ]
    dataset_text = "\n".join(
        json.dumps(record, ensure_ascii=False) for record in records
    )
    train_path.write_text(dataset_text, encoding="utf-8")
    eval_path.write_text(dataset_text, encoding="utf-8")

    main(
        [
            "train-tokenizer",
            "--input",
            str(train_path),
            "--output",
            str(tokenizer_path),
            "--vocab-size",
            "512",
            "--min-frequency",
            "1",
        ]
    )
    capsys.readouterr()

    prepare_exit_code = main(
        [
            "prepare-lm-dataset",
            "--input",
            str(train_path),
            "--tokenizer",
            str(tokenizer_path),
            "--output",
            str(cache_path),
            "--sequence-length",
            "32",
            "--loss-mode",
            "answer-only",
        ]
    )
    prepared = json.loads(capsys.readouterr().out)

    assert prepare_exit_code == 0
    assert cache_path.exists()
    assert prepared["count"] == 2
    assert prepared["metadata"]["loss_mode"] == "answer-only"

    train_exit_code = main(
        [
            "train-lm",
            "--train",
            str(train_path),
            "--eval",
            str(eval_path),
            "--tokenizer",
            str(tokenizer_path),
            "--output-dir",
            str(output_dir),
            "--config",
            "debug",
            "--steps",
            "2",
            "--batch-size",
            "2",
            "--sequence-length",
            "32",
            "--loss-mode",
            "answer-only",
            "--eval-every",
            "1",
            "--eval-batches",
            "1",
            "--save-every",
            "2",
            "--cache-dir",
            str(cache_dir),
            "--cpu",
        ]
    )
    trained = json.loads(capsys.readouterr().out)

    assert train_exit_code == 0
    assert trained["final_step"] == 2
    assert (output_dir / "metrics.jsonl").exists()
    assert (output_dir / "checkpoints" / "step_000002.pt").exists()
