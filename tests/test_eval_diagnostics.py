from __future__ import annotations

import json

from ai_brain.cli import main
from ai_brain.eval.compare import compare_evals
from ai_brain.eval.diagnostics import analyze_eval


def _prediction(
    *,
    index: int,
    task_type: str,
    expected: str,
    predicted: str,
    raw_generation: str,
    normalized_exact_match: bool,
    false_answer: bool = False,
    tokens_generated: int = 3,
) -> dict[str, object]:
    return {
        "id": f"{task_type}:{index:06d}",
        "task_type": task_type,
        "task_group": task_type.split(".", 1)[0],
        "prompt": f"prompt {index}",
        "expected": expected,
        "predicted": predicted,
        "raw_generation": raw_generation,
        "tokens_generated": tokens_generated,
        "exact_match": predicted == expected,
        "normalized_exact_match": normalized_exact_match,
        "false_answer": false_answer,
    }


def _write_predictions(path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n\n",
        encoding="utf-8",
    )


def _sample_predictions() -> list[dict[str, object]]:
    rows = [
        _prediction(
            index=0,
            task_type="arithmetic.add",
            expected="5",
            predicted="0",
            raw_generation="0\n<|end|>",
            normalized_exact_match=False,
            tokens_generated=3,
        ),
        _prediction(
            index=1,
            task_type="arithmetic.add",
            expected="7",
            predicted="",
            raw_generation="<|end|>",
            normalized_exact_match=False,
            tokens_generated=1,
        ),
        _prediction(
            index=2,
            task_type="logic.and_or",
            expected="Да.",
            predicted="да",
            raw_generation="да\n<|end|>",
            normalized_exact_match=True,
            tokens_generated=3,
        ),
        _prediction(
            index=3,
            task_type="epistemic.insufficient_info",
            expected="Недостаточно информации",
            predicted="7",
            raw_generation="7\n<|end|>",
            normalized_exact_match=False,
            false_answer=True,
            tokens_generated=3,
        ),
    ]
    rows.extend(
        _prediction(
            index=100 + index,
            task_type="sorting.ascending",
            expected="1, 2, 3",
            predicted="0",
            raw_generation="0\n<|end|>",
            normalized_exact_match=False,
            tokens_generated=3,
        )
        for index in range(20)
    )
    return rows


def test_analyze_eval_creates_diagnostics_json_and_md(tmp_path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    _write_predictions(predictions_path, _sample_predictions())

    result = analyze_eval(
        predictions_path=predictions_path,
        output_dir=output_dir,
        top_k=5,
        max_samples_per_task=2,
    )

    assert (output_dir / "diagnostics.json").exists()
    assert (output_dir / "diagnostics.md").exists()
    assert result["diagnostics"]["overall"]["count"] == 24
    assert "# Eval Diagnostics" in (output_dir / "diagnostics.md").read_text(
        encoding="utf-8"
    )


def test_analyze_eval_computes_empty_prediction_rate(tmp_path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    _write_predictions(predictions_path, _sample_predictions())

    diagnostics = analyze_eval(
        predictions_path=predictions_path,
        output_dir=output_dir,
    )["diagnostics"]

    assert diagnostics["overall"]["empty_prediction_count"] == 1
    assert diagnostics["overall"]["empty_prediction_rate"] == 1 / 24


def test_analyze_eval_computes_immediate_end_rate(tmp_path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    _write_predictions(predictions_path, _sample_predictions())

    diagnostics = analyze_eval(
        predictions_path=predictions_path,
        output_dir=output_dir,
    )["diagnostics"]

    assert diagnostics["overall"]["immediate_end_count"] == 1
    assert diagnostics["overall"]["immediate_end_rate"] == 1 / 24


def test_analyze_eval_backfills_final_answer_fields_for_old_predictions(
    tmp_path,
) -> None:
    predictions_path = tmp_path / "old_predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    rows = [
        _prediction(
            index=0,
            task_type="arithmetic.add",
            expected="ones: wrong\nanswer: 134",
            predicted="different trace\nOUT 1 3 4",
            raw_generation="different trace\nOUT 1 3 4\n<|end|>",
            normalized_exact_match=False,
        )
    ]
    _write_predictions(predictions_path, rows)

    diagnostics = analyze_eval(
        predictions_path=predictions_path,
        output_dir=output_dir,
    )["diagnostics"]

    assert diagnostics["overall"]["normalized_exact_match"] == 0.0
    assert diagnostics["overall"]["final_normalized_exact_match"] == 1.0
    sample = diagnostics["by_task_type"]["arithmetic.add"]["error_samples"][0]
    assert sample["final_expected"] == "134"
    assert sample["final_predicted"] == "1 3 4"


def test_analyze_eval_computes_top_predictions(tmp_path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    _write_predictions(predictions_path, _sample_predictions())

    diagnostics = analyze_eval(
        predictions_path=predictions_path,
        output_dir=output_dir,
        top_k=2,
    )["diagnostics"]

    assert diagnostics["top_predictions"] == [
        {"predicted": "0", "count": 21},
        {"predicted": "", "count": 1},
    ]


def test_analyze_eval_groups_by_task_type_and_task_group(tmp_path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    _write_predictions(predictions_path, _sample_predictions())

    diagnostics = analyze_eval(
        predictions_path=predictions_path,
        output_dir=output_dir,
    )["diagnostics"]

    assert diagnostics["by_group"]["arithmetic"]["count"] == 2
    assert diagnostics["by_task_type"]["sorting.ascending"]["count"] == 20
    assert diagnostics["by_task_type"]["logic.and_or"]["normalized_exact_match"] == 1.0


def test_analyze_eval_stores_error_samples_and_correct_samples(tmp_path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    _write_predictions(predictions_path, _sample_predictions())

    diagnostics = analyze_eval(
        predictions_path=predictions_path,
        output_dir=output_dir,
        max_samples_per_task=1,
    )["diagnostics"]

    arithmetic = diagnostics["by_task_type"]["arithmetic.add"]
    logic = diagnostics["by_task_type"]["logic.and_or"]
    assert len(arithmetic["error_samples"]) == 1
    assert arithmetic["correct_samples"] == []
    assert logic["error_samples"] == []
    assert len(logic["correct_samples"]) == 1
    assert diagnostics["suspicious_task_types"][0]["task_type"] == "sorting.ascending"


def _summary(
    overall: float, groups: dict[str, float], tasks: dict[str, tuple[int, float]]
):
    return {
        "overall": {
            "count": 100,
            "normalized_exact_match": overall,
            "false_answer_rate": 0.01,
        },
        "by_group": {
            group: {
                "count": 10,
                "normalized_exact_match": score,
                "false_answer_rate": 0.0,
            }
            for group, score in groups.items()
        },
        "by_task_type": {
            task_type: {
                "count": count,
                "normalized_exact_match": score,
                "false_answer_rate": 0.0,
            }
            for task_type, (count, score) in tasks.items()
        },
    }


def _write_summary(path, summary) -> None:
    path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")


def test_compare_evals_creates_comparison_json_and_md(tmp_path) -> None:
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    output_dir = tmp_path / "comparison"
    _write_summary(
        left_path, _summary(0.1, {"logic": 0.2}, {"logic.and_or": (20, 0.2)})
    )
    _write_summary(
        right_path, _summary(0.3, {"logic": 0.4}, {"logic.and_or": (20, 0.4)})
    )

    result = compare_evals(
        left_summary_path=left_path,
        right_summary_path=right_path,
        left_label="debug",
        right_label="tiny",
        output_dir=output_dir,
    )

    assert (output_dir / "comparison.json").exists()
    assert (output_dir / "comparison.md").exists()
    assert result["comparison"]["left_label"] == "debug"
    assert "# Eval Comparison" in (output_dir / "comparison.md").read_text(
        encoding="utf-8"
    )


def test_compare_evals_computes_overall_group_task_deltas(tmp_path) -> None:
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    output_dir = tmp_path / "comparison"
    _write_summary(
        left_path,
        _summary(0.1, {"logic": 0.2}, {"logic.and_or": (20, 0.2)}),
    )
    _write_summary(
        right_path,
        _summary(0.35, {"logic": 0.5}, {"logic.and_or": (20, 0.6)}),
    )

    comparison = compare_evals(
        left_summary_path=left_path,
        right_summary_path=right_path,
        output_dir=output_dir,
    )["comparison"]

    assert comparison["overall"]["delta_normalized_exact_match"] == 0.24999999999999997
    assert comparison["by_group"]["logic"]["delta_normalized_exact_match"] == 0.3
    assert (
        comparison["by_task_type"]["logic.and_or"]["delta_normalized_exact_match"]
        == 0.39999999999999997
    )
    assert comparison["most_improved_task_types"][0]["task_type"] == "logic.and_or"


def test_compare_evals_detects_still_failed_task_types(tmp_path) -> None:
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    output_dir = tmp_path / "comparison"
    _write_summary(
        left_path,
        _summary(0.1, {}, {"sorting.ascending": (20, 0.0)}),
    )
    _write_summary(
        right_path,
        _summary(0.2, {}, {"sorting.ascending": (25, 0.0)}),
    )

    comparison = compare_evals(
        left_summary_path=left_path,
        right_summary_path=right_path,
        output_dir=output_dir,
    )["comparison"]

    assert comparison["still_failed_task_types"][0]["task_type"] == "sorting.ascending"


def test_cli_analyze_eval(tmp_path, capsys) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_dir = tmp_path / "diagnostics"
    _write_predictions(predictions_path, _sample_predictions())

    exit_code = main(
        [
            "analyze-eval",
            "--predictions",
            str(predictions_path),
            "--output-dir",
            str(output_dir),
            "--top-k",
            "3",
            "--max-samples-per-task",
            "1",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["overall"]["count"] == 24
    assert (output_dir / "diagnostics.json").exists()


def test_cli_compare_evals(tmp_path, capsys) -> None:
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    output_dir = tmp_path / "comparison"
    _write_summary(
        left_path, _summary(0.1, {"logic": 0.2}, {"logic.and_or": (20, 0.2)})
    )
    _write_summary(
        right_path, _summary(0.3, {"logic": 0.4}, {"logic.and_or": (20, 0.4)})
    )

    exit_code = main(
        [
            "compare-evals",
            "--left-summary",
            str(left_path),
            "--right-summary",
            str(right_path),
            "--left-label",
            "debug",
            "--right-label",
            "tiny",
            "--output-dir",
            str(output_dir),
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["right_label"] == "tiny"
    assert (output_dir / "comparison.json").exists()
