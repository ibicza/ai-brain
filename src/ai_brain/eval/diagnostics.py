from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ai_brain.eval.metrics import task_group

_REQUIRED_PREDICTION_FIELDS = (
    "task_type",
    "prompt",
    "expected",
    "predicted",
    "raw_generation",
    "exact_match",
    "normalized_exact_match",
    "false_answer",
)


def analyze_eval(
    *,
    predictions_path: Path,
    output_dir: Path,
    top_k: int = 20,
    max_samples_per_task: int = 10,
) -> dict[str, Any]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if max_samples_per_task < 0:
        raise ValueError("max_samples_per_task must be non-negative")

    predictions = list(_iter_predictions(predictions_path))
    output_dir.mkdir(parents=True, exist_ok=True)

    diagnostics = {
        "predictions_path": str(predictions_path),
        "overall": _stats_for(predictions),
        "top_predictions": _top_predictions(predictions, top_k=top_k),
        "by_group": _analyze_by_group(predictions),
        "by_task_type": _analyze_by_task_type(
            predictions,
            top_k=top_k,
            max_samples_per_task=max_samples_per_task,
        ),
    }
    task_type_items = [
        {"task_type": task_type, **stats}
        for task_type, stats in diagnostics["by_task_type"].items()
    ]
    diagnostics["worst_task_types"] = sorted(
        task_type_items,
        key=lambda item: (
            item["normalized_exact_match"],
            -item["count"],
            item["task_type"],
        ),
    )[:top_k]
    diagnostics["best_task_types"] = sorted(
        task_type_items,
        key=lambda item: (
            -item["normalized_exact_match"],
            -item["count"],
            item["task_type"],
        ),
    )[:top_k]
    diagnostics["suspicious_task_types"] = [
        item
        for item in task_type_items
        if item["count"] >= 20
        and (
            item["normalized_exact_match"] == 0.0
            or item["empty_prediction_rate"] >= 0.2
            or item["false_answer_rate"] >= 0.1
        )
    ]
    diagnostics["suspicious_task_types"] = sorted(
        diagnostics["suspicious_task_types"],
        key=lambda item: (
            item["normalized_exact_match"],
            -item["empty_prediction_rate"],
            -item["false_answer_rate"],
            -item["count"],
            item["task_type"],
        ),
    )

    diagnostics_path = output_dir / "diagnostics.json"
    markdown_path = output_dir / "diagnostics.md"
    diagnostics_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(
        _render_diagnostics_markdown(diagnostics), encoding="utf-8"
    )

    return {
        "output_dir": str(output_dir),
        "diagnostics_path": str(diagnostics_path),
        "markdown_path": str(markdown_path),
        "diagnostics": diagnostics,
    }


def _iter_predictions(path: Path):
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            prediction = json.loads(stripped)
            missing = [
                field
                for field in _REQUIRED_PREDICTION_FIELDS
                if field not in prediction
            ]
            if missing:
                raise ValueError(
                    f"Prediction row {line_number} in {path} is missing required fields: "
                    f"{', '.join(missing)}"
                )
            if "task_group" not in prediction:
                prediction["task_group"] = task_group(str(prediction["task_type"]))
            if "tokens_generated" not in prediction:
                prediction["tokens_generated"] = 0
            if "id" not in prediction:
                prediction["id"] = f"{prediction['task_type']}:{line_number - 1:06d}"
            yield prediction


def _stats_for(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(predictions)
    if count == 0:
        return {
            "count": 0,
            "exact_match": 0.0,
            "normalized_exact_match": 0.0,
            "false_answer_count": 0,
            "false_answer_rate": 0.0,
            "empty_prediction_count": 0,
            "empty_prediction_rate": 0.0,
            "immediate_end_count": 0,
            "immediate_end_rate": 0.0,
            "avg_tokens_generated": 0.0,
            "min_tokens_generated": 0,
            "max_tokens_generated": 0,
        }

    exact_count = sum(bool(prediction["exact_match"]) for prediction in predictions)
    normalized_count = sum(
        bool(prediction["normalized_exact_match"]) for prediction in predictions
    )
    false_answer_count = sum(
        bool(prediction["false_answer"]) for prediction in predictions
    )
    empty_prediction_count = sum(
        str(prediction.get("predicted", "")).strip() == "" for prediction in predictions
    )
    immediate_end_count = sum(
        _is_immediate_end(prediction) for prediction in predictions
    )
    token_counts = [
        _safe_int(prediction.get("tokens_generated", 0)) for prediction in predictions
    ]

    return {
        "count": count,
        "exact_match": exact_count / count,
        "normalized_exact_match": normalized_count / count,
        "false_answer_count": false_answer_count,
        "false_answer_rate": false_answer_count / count,
        "empty_prediction_count": empty_prediction_count,
        "empty_prediction_rate": empty_prediction_count / count,
        "immediate_end_count": immediate_end_count,
        "immediate_end_rate": immediate_end_count / count,
        "avg_tokens_generated": sum(token_counts) / count,
        "min_tokens_generated": min(token_counts),
        "max_tokens_generated": max(token_counts),
    }


def _is_immediate_end(prediction: dict[str, Any]) -> bool:
    raw_generation = str(prediction.get("raw_generation", "")).strip()
    return raw_generation.startswith(("<|end|>", "<|eos|>"))


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _top_predictions(
    predictions: list[dict[str, Any]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    counter = Counter(
        str(prediction.get("predicted", "")) for prediction in predictions
    )
    return [
        {"predicted": predicted, "count": count}
        for predicted, count in sorted(
            counter.items(), key=lambda item: (-item[1], item[0])
        )[:top_k]
    ]


def _analyze_by_group(predictions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        buckets[str(prediction["task_group"])].append(prediction)
    return {group: _stats_for(bucket) for group, bucket in sorted(buckets.items())}


def _analyze_by_task_type(
    predictions: list[dict[str, Any]],
    *,
    top_k: int,
    max_samples_per_task: int,
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        buckets[str(prediction["task_type"])].append(prediction)

    result: dict[str, dict[str, Any]] = {}
    for task_type_name, bucket in sorted(buckets.items()):
        stats = _stats_for(bucket)
        stats["top_predictions"] = _top_predictions(bucket, top_k=top_k)
        stats["error_samples"] = _samples(
            [
                prediction
                for prediction in bucket
                if not prediction["normalized_exact_match"]
            ],
            max_samples=max_samples_per_task,
        )
        stats["correct_samples"] = _samples(
            [
                prediction
                for prediction in bucket
                if prediction["normalized_exact_match"]
            ],
            max_samples=max_samples_per_task,
        )
        result[task_type_name] = stats
    return result


def _samples(
    predictions: list[dict[str, Any]],
    *,
    max_samples: int,
) -> list[dict[str, Any]]:
    return [
        {
            "id": str(prediction.get("id", "")),
            "prompt": str(prediction["prompt"]),
            "expected": str(prediction["expected"]),
            "predicted": str(prediction["predicted"]),
            "raw_generation": str(prediction["raw_generation"]),
        }
        for prediction in predictions[:max_samples]
    ]


def _render_diagnostics_markdown(diagnostics: dict[str, Any]) -> str:
    lines = ["# Eval Diagnostics", ""]
    overall = diagnostics["overall"]
    lines.extend(
        [
            "## Overall",
            "",
            f"- Count: {overall['count']}",
            f"- Exact match: {_fmt_rate(overall['exact_match'])}",
            f"- Normalized exact match: {_fmt_rate(overall['normalized_exact_match'])}",
            f"- False answer rate: {_fmt_rate(overall['false_answer_rate'])}",
            f"- Empty prediction rate: {_fmt_rate(overall['empty_prediction_rate'])}",
            f"- Immediate end rate: {_fmt_rate(overall['immediate_end_rate'])}",
            f"- Avg tokens generated: {overall['avg_tokens_generated']:.2f}",
            "",
            "## By Group",
            "",
            "| Group | Count | Normalized EM | False Answer Rate | Empty Rate | Avg Tokens |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for group, stats in diagnostics["by_group"].items():
        lines.append(
            f"| {group} | {stats['count']} | {_fmt_rate(stats['normalized_exact_match'])} | "
            f"{_fmt_rate(stats['false_answer_rate'])} | {_fmt_rate(stats['empty_prediction_rate'])} | "
            f"{stats['avg_tokens_generated']:.2f} |"
        )

    _append_task_table(lines, "Worst Task Types", diagnostics["worst_task_types"])
    _append_task_table(lines, "Best Task Types", diagnostics["best_task_types"])
    _append_task_table(
        lines, "Suspicious Task Types", diagnostics["suspicious_task_types"]
    )

    lines.extend(
        [
            "",
            "## Top Predicted Answers",
            "",
            "| Predicted | Count |",
            "|---|---:|",
        ]
    )
    for item in diagnostics["top_predictions"]:
        lines.append(f"| {_md_cell(item['predicted'])} | {item['count']} |")

    lines.extend(["", "## Error Samples by Task Type", ""])
    for task_type_name, stats in diagnostics["by_task_type"].items():
        samples = stats["error_samples"]
        if not samples:
            continue
        lines.extend([f"### {task_type_name}", ""])
        for sample in samples:
            lines.extend(
                [
                    f"- `{sample['id']}`",
                    f"  - Prompt: {_md_cell(sample['prompt'])}",
                    f"  - Expected: {_md_cell(sample['expected'])}",
                    f"  - Predicted: {_md_cell(sample['predicted'])}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _append_task_table(
    lines: list[str], title: str, rows: list[dict[str, Any]]
) -> None:
    lines.extend(
        [
            "",
            f"## {title}",
            "",
            "| Task Type | Count | Normalized EM | False Answer Rate | Empty Rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['task_type']} | {row['count']} | {_fmt_rate(row['normalized_exact_match'])} | "
            f"{_fmt_rate(row['false_answer_rate'])} | {_fmt_rate(row['empty_prediction_rate'])} |"
        )


def _fmt_rate(value: float) -> str:
    return f"{value:.4f}"


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
