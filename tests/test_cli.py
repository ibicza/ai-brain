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
