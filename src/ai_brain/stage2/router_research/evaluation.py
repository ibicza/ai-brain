"""Assistive-only route metrics and abstention evaluation."""

from __future__ import annotations

from collections import Counter
from typing import Any


def evaluate(
    model, rows: list[dict[str, Any]], *, threshold: float = 0.0
) -> dict[str, Any]:
    correct = 0
    abstained = 0
    slice_counts: Counter[str] = Counter()
    slice_correct: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    label_correct: Counter[str] = Counter()
    scored_rows: list[tuple[float, bool]] = []
    class_scores: dict[str, list[tuple[float, bool]]] = {}
    for row in rows:
        scores = model.scores(row["text"])
        predicted = max(scores, key=lambda label: (scores[label], label))
        confidence = scores[predicted]
        scored_rows.append((confidence, predicted == row["label"]))
        for label, score in scores.items():
            class_scores.setdefault(label, []).append((score, row["label"] == label))
        if confidence < threshold:
            abstained += 1
            continue
        correct += int(predicted == row["label"])
        label_counts[row["label"]] += 1
        label_correct[row["label"]] += int(predicted == row["label"])
        slice_counts[row["slice"]] += 1
        slice_correct[row["slice"]] += int(predicted == row["label"])
    covered = len(rows) - abstained
    by_label = {key: label_correct[key] / count for key, count in label_counts.items()}
    by_slice = {key: slice_correct[key] / count for key, count in slice_counts.items()}
    aucs = [_roc_auc(values) for values in class_scores.values()]
    average_precisions = [
        _average_precision(values) for values in class_scores.values()
    ]
    known_labels = {
        "FACT_QUERY",
        "SKILL_REQUEST",
        "TOOL_REQUEST",
    }
    known_total = sum(label_counts[label] for label in known_labels)
    known_correct = sum(label_correct[label] for label in known_labels)
    return {
        "top1": correct / len(rows) if rows else 0.0,
        "covered_accuracy": correct / covered if covered else 0.0,
        "coverage": covered / len(rows) if rows else 0.0,
        "false_exact_authority": 0,
        "known_route_recall": known_correct / known_total if known_total else 0.0,
        "unsupported_abstention": by_label.get("UNSUPPORTED", 0.0),
        "ambiguous_abstention": by_label.get("CLARIFICATION", 0.0),
        "composite_detection": by_label.get("COMPOSITE_REQUIRED", 0.0),
        "cross_domain_error_rate": 1.0 - by_slice.get("HARD_CROSS_DOMAIN", 0.0),
        "macro_ovr_auroc": sum(aucs) / len(aucs) if aucs else 0.0,
        "macro_ovr_auprc": (
            sum(average_precisions) / len(average_precisions)
            if average_precisions
            else 0.0
        ),
        "risk_coverage": _risk_coverage(scored_rows),
        "by_label": by_label,
        "by_slice": by_slice,
    }


def _roc_auc(values: list[tuple[float, bool]]) -> float:
    positives = sum(is_positive for _, is_positive in values)
    negatives = len(values) - positives
    if not positives or not negatives:
        return 0.0
    ordered = sorted(values, key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2
        rank_sum += average_rank * sum(
            is_positive for _, is_positive in ordered[index:end]
        )
        index = end
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _average_precision(values: list[tuple[float, bool]]) -> float:
    positives = sum(is_positive for _, is_positive in values)
    if not positives:
        return 0.0
    true_positives = 0
    precision_sum = 0.0
    for rank, (_, is_positive) in enumerate(
        sorted(values, key=lambda item: item[0], reverse=True), start=1
    ):
        if is_positive:
            true_positives += 1
            precision_sum += true_positives / rank
    return precision_sum / positives


def _risk_coverage(values: list[tuple[float, bool]]) -> dict[str, dict[str, float]]:
    ordered = sorted(values, key=lambda item: item[0], reverse=True)
    result: dict[str, dict[str, float]] = {}
    for target in (0.25, 0.5, 0.75, 0.9, 1.0):
        count = max(1, round(len(ordered) * target)) if ordered else 0
        selected = ordered[:count]
        errors = sum(not correct for _, correct in selected)
        result[format(target, ".2f")] = {
            "coverage": count / len(ordered) if ordered else 0.0,
            "risk": errors / count if count else 0.0,
        }
    return result
