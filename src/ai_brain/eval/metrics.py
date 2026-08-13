from __future__ import annotations

from collections import defaultdict
from typing import Any

from ai_brain.eval.normalize import is_epistemic_task


def task_group(task_type: str) -> str:
    return task_type.split(".", 1)[0]


def summarize_predictions(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": _summarize_slice(predictions),
        "by_group": _summarize_by_key(predictions, key="task_group"),
        "by_task_type": _summarize_by_key(predictions, key="task_type"),
        "epistemic": _summarize_epistemic(predictions),
    }


def _summarize_by_key(
    predictions: list[dict[str, Any]],
    *,
    key: str,
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        buckets[str(prediction[key])].append(prediction)
    return {
        bucket_key: _summarize_slice(bucket)
        for bucket_key, bucket in sorted(buckets.items())
    }


def _summarize_slice(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(predictions)
    if count == 0:
        return {
            "count": 0,
            "exact_match": 0.0,
            "normalized_exact_match": 0.0,
            "final_exact_match": 0.0,
            "final_normalized_exact_match": 0.0,
            "false_answer_rate": 0.0,
        }

    exact_count = sum(bool(prediction["exact_match"]) for prediction in predictions)
    normalized_count = sum(
        bool(prediction["normalized_exact_match"]) for prediction in predictions
    )
    final_exact_count = sum(
        bool(prediction.get("final_exact_match", prediction["exact_match"]))
        for prediction in predictions
    )
    final_normalized_count = sum(
        bool(
            prediction.get(
                "final_normalized_exact_match",
                prediction["normalized_exact_match"],
            )
        )
        for prediction in predictions
    )
    false_answer_count = sum(
        bool(prediction["false_answer"]) for prediction in predictions
    )
    return {
        "count": count,
        "exact_match": exact_count / count,
        "normalized_exact_match": normalized_count / count,
        "final_exact_match": final_exact_count / count,
        "final_normalized_exact_match": final_normalized_count / count,
        "false_answer_count": false_answer_count,
        "false_answer_rate": false_answer_count / count,
    }


def _summarize_epistemic(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    epistemic_predictions = [
        prediction
        for prediction in predictions
        if is_epistemic_task(str(prediction["task_type"]))
    ]
    summary = _summarize_slice(epistemic_predictions)
    summary["epistemic_count"] = summary["count"]
    summary["epistemic_exact_match"] = summary["exact_match"]
    return summary
