"""Deterministic Stage-2 retrieval and scale measurements."""

from __future__ import annotations

import statistics
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict
from typing import Any

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.models import content_hash
from ai_brain.stage2.models import RetrievalMode
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage2.retrieval import assistive_query, retrieve_assistive


def evaluate_deterministic_baseline(
    registry: SkillRegistry,
    memory: RuleMemory,
    rows: list[dict[str, Any]],
    mode: RetrievalMode,
) -> dict[str, Any]:
    known = [row for row in rows if row.get("target_skill_id")]
    ranks: list[int] = []
    latencies: list[float] = []
    wrong = Counter()
    for index, row in enumerate(known):
        query = assistive_query(
            row["text"],
            row["language"],
            query_id_factory=lambda i=index: f"baseline-{mode}-{i}",
        )
        started = time.perf_counter()
        result = retrieve_assistive(query, registry, memory, mode=mode, top_k=5)
        latencies.append((time.perf_counter() - started) * 1000)
        candidate_ids = [item.skill_id for item in result.candidates]
        rank = (
            candidate_ids.index(row["target_skill_id"]) + 1
            if row["target_skill_id"] in candidate_ids
            else 90
        )
        ranks.append(rank)
        if rank != 1 and candidate_ids:
            _categorize_error(
                registry.records[row["target_skill_id"]],
                registry.records[candidate_ids[0]],
                wrong,
            )
    hard_indices = [
        index
        for index, row in enumerate(known)
        if row.get("query_kind") == "hard_neighbor"
    ]
    return {
        **_rank_metrics(ranks),
        "known_count": len(known),
        "hard_neighbor_top1": (
            sum(ranks[index] == 1 for index in hard_indices) / len(hard_indices)
            if hard_indices
            else 0.0
        ),
        "wrong_family_rate": wrong["family"] / len(known) if known else 0.0,
        "wrong_register_rate": wrong["register"] / len(known) if known else 0.0,
        "wrong_destination_rate": (wrong["destination"] / len(known) if known else 0.0),
        "wrong_order_rate": wrong["order"] / len(known) if known else 0.0,
        "latency_ms_mean": statistics.fmean(latencies) if latencies else 0.0,
        "latency_ms_p95": _percentile(latencies, 0.95),
        "trusted_selector": False,
    }


def evaluate_unknown_policy(
    registry: SkillRegistry,
    memory: RuleMemory,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    negatives = [row for row in rows if not row.get("target_skill_id")]
    auto_selected = 0
    exact_marked = 0
    for index, row in enumerate(negatives):
        query = assistive_query(
            row["text"],
            row["language"],
            query_id_factory=lambda i=index: f"negative-{i}",
        )
        result = retrieve_assistive(query, registry, memory, top_k=5)
        auto_selected += int(result.recommended_next_action == "SELECT_EXACT")
        exact_marked += int(result.exact_match)
    return {
        "count": len(negatives),
        "automatic_selection_count": auto_selected,
        "exact_marked_count": exact_marked,
        "safe_rate": (
            1.0 - (auto_selected + exact_marked) / len(negatives) if negatives else 1.0
        ),
    }


def measure_catalog_scale(registry: SkillRegistry) -> list[dict[str, Any]]:
    base = [
        " ".join(
            (
                item.canonical_name_ru,
                item.canonical_name_en,
                item.effect_summary,
                *item.aliases_ru,
                *item.aliases_en,
                *item.controlled_examples_ru,
                *item.controlled_examples_en,
            )
        )
        for item in registry.active_records()
    ]
    query_tokens = set(
        "move items A B destination preserve unchanged".casefold().split()
    )
    results = []
    for entry_count in (100, 500, 1_000, 5_000, 10_000):
        tracemalloc.start()
        started = time.perf_counter()
        entries = [base[index % len(base)] for index in range(entry_count)]
        index = [set(text.casefold().split()) for text in entries]
        build_ms = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        started = time.perf_counter()
        max(
            enumerate(index),
            key=lambda item: len(item[1] & query_tokens),
        )
        query_ms = (time.perf_counter() - started) * 1000
        results.append(
            {
                "unique_skills": len(registry.active_records()),
                "catalog_text_entries": entry_count,
                "index_entries": len(index),
                "query_examples": entry_count,
                "index_build_ms": build_ms,
                "lexical_query_ms": query_ms,
                "peak_memory_bytes": peak,
            }
        )
    return results


def registry_load_latency(path, *, repeats: int = 5) -> dict[str, float]:
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        SkillRegistry.load(path)
        values.append((time.perf_counter() - started) * 1000)
    return {"mean_ms": statistics.fmean(values), "max_ms": max(values)}


def _rank_metrics(ranks: list[int]) -> dict[str, float]:
    if not ranks:
        return {"top1": 0.0, "top3": 0.0, "top5": 0.0, "mrr": 0.0}
    return {
        "top1": sum(rank <= 1 for rank in ranks) / len(ranks),
        "top3": sum(rank <= 3 for rank in ranks) / len(ranks),
        "top5": sum(rank <= 5 for rank in ranks) / len(ranks),
        "mrr": sum(1.0 / rank for rank in ranks) / len(ranks),
    }


def _categorize_error(target, prediction, wrong: Counter) -> None:
    if target.semantic_family != prediction.semantic_family:
        wrong["family"] += 1
    target_effect = target.effect_schema
    prediction_effect = prediction.effect_schema
    if target_effect.get("inputs") != prediction_effect.get("inputs"):
        wrong["register"] += 1
    if target_effect.get("outputs") != prediction_effect.get("outputs"):
        wrong["destination"] += 1
    if target_effect.get("phase_constraints") != prediction_effect.get(
        "phase_constraints"
    ):
        wrong["order"] += 1


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    return sorted(values)[min(len(values) - 1, int(len(values) * fraction))]


def benchmark_fingerprint(results: dict[str, Any]) -> str:
    return content_hash(
        asdict(results) if hasattr(results, "__dataclass_fields__") else results
    )
