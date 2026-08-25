"""Slice, hard-neighbor, and novelty metrics for fair learned retrieval."""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from ai_brain.stage2.learned import (
    LearnedRetriever,
    _abstention_metrics,
    _ranking_metrics,
    _score_rows,
)


def evaluate_fair_retriever(
    retriever: LearnedRetriever, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    expanded = list(rows)
    counterfactuals = []
    for row in rows:
        if row.get("counterfactual_text") and row.get("counterfactual_target_skill_id"):
            counterfactuals.append(
                {
                    **row,
                    "query_id": f"{row['query_id']}-counterfactual",
                    "text": row["counterfactual_text"],
                    "target_skill_id": row["counterfactual_target_skill_id"],
                    "neighbor_skill_id": row["target_skill_id"],
                    "counterfactual_side": True,
                }
            )
    scored = _score_rows(retriever, expanded)
    scored_counterfactuals = _score_rows(retriever, counterfactuals)
    known = [item for item in scored if item["known_target"]]
    by_slice = {}
    for slice_name in sorted({item["evaluation_slice"] for item in scored}):
        subset = [
            item
            for item in scored
            if item["evaluation_slice"] == slice_name and item["known_target"]
        ]
        by_slice[slice_name] = {**_ranking_metrics(subset), "count": len(subset)}
    abstention = _abstention_metrics(scored, retriever.threshold)
    unknown_rows = [item for item in scored if not item["known_target"]]
    unknown_family = {}
    for family in sorted({item["unknown_family"] for item in unknown_rows}):
        subset = [item for item in unknown_rows if item["unknown_family"] == family]
        unknown_family[str(family)] = {
            "count": len(subset),
            "false_known_rate": sum(
                item["score"] >= retriever.threshold for item in subset
            )
            / len(subset),
        }
    return {
        **_ranking_metrics(known),
        "known_count": len(known),
        "unknown_count": len(unknown_rows),
        "by_slice": by_slice,
        "hard_neighbor": _hard_neighbor_metrics(scored, scored_counterfactuals),
        "abstention": {
            **abstention,
            "ambiguous_abstention": _family_abstention(
                [item for item in unknown_rows if item["ambiguous"]],
                retriever.threshold,
            ),
            "per_unknown_family": unknown_family,
        },
        "failure_samples": [
            {
                "query_id": item["query_id"],
                "slice": item["evaluation_slice"],
                "target": item["target"],
                "prediction": item["prediction"],
                "rank": item["rank"],
                "score": item["score"],
            }
            for item in known
            if item["rank"] != 1
        ][:30],
    }


def _hard_neighbor_metrics(scored, counterfactuals):
    hard = [item for item in scored if item["query_pair_id"]]
    margins = [
        item["target_score"] - item["neighbor_score"]
        for item in hard
        if item["target_score"] is not None and item["neighbor_score"] is not None
    ]
    pairwise = [value > 0 for value in margins]
    original = {item["query_pair_id"]: item for item in hard}
    switched = []
    for item in counterfactuals:
        base = original.get(item["query_pair_id"])
        if base is not None:
            switched.append(base["rank"] == 1 and item["rank"] == 1)
    errors = Counter(item["changed_field"] for item in hard if item["rank"] != 1)
    return {
        **_ranking_metrics(hard),
        "count": len(hard),
        "pairwise_target_over_neighbor_accuracy": (
            sum(pairwise) / len(pairwise) if pairwise else 0.0
        ),
        "target_neighbor_score_margin_mean": (
            statistics.fmean(margins) if margins else 0.0
        ),
        "one_field_sensitivity": sum(pairwise) / len(pairwise) if pairwise else 0.0,
        "counterfactual_top1_switch_accuracy": (
            sum(switched) / len(switched) if switched else 0.0
        ),
        "error_by_changed_field": dict(errors),
    }


def _family_abstention(rows, threshold):
    return sum(item["score"] < threshold for item in rows) / len(rows) if rows else 0.0
