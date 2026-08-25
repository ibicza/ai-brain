"""Automatic leakage and corpus-overlap diagnostics for M-25.1."""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any

from ai_brain.stage2.fair_dataset import NEUTRAL_WRAPPERS
from ai_brain.stage2.models import SkillRecord
from ai_brain.stage2.skill_corpora import build_skill_corpus


def diagnose_label_leakage(
    train_rows: list[dict[str, Any]],
    evaluation_rows: list[dict[str, Any]],
    skills: list[SkillRecord],
) -> dict[str, Any]:
    wrapper = _wrapper_only_classifier(train_rows, evaluation_rows)
    shape = _shape_only_classifier(train_rows, evaluation_rows)
    shape = {**shape, "alert": shape["auroc"] > 0.60, "alert_threshold": 0.60}
    substring = exact_catalog_substring_rates(evaluation_rows, skills)
    corpora = {
        condition: corpus_overlap_statistics(evaluation_rows, skills, condition)
        for condition in ("rich", "sanitized", "minimal")
    }
    return {
        "wrapper_only": {
            **wrapper,
            "alert": wrapper["auroc"] > 0.60,
            "alert_threshold": 0.60,
        },
        "length_punctuation": shape,
        "exact_catalog_substring": substring,
        "query_to_skill_corpus_overlap": corpora,
    }


def exact_catalog_substring_rates(
    rows: list[dict[str, Any]], skills: list[SkillRecord]
) -> dict[str, Any]:
    phrases = []
    for skill in skills:
        phrases.extend(
            (skill.skill_id, phrase.casefold())
            for phrase in (
                *skill.aliases_ru,
                *skill.aliases_en,
                *skill.controlled_examples_ru,
                *skill.controlled_examples_en,
            )
        )
    grouped: defaultdict[str, list[bool]] = defaultdict(list)
    examples = []
    for row in rows:
        text = " ".join(row["text"].casefold().split())
        matches = [skill_id for skill_id, phrase in phrases if phrase in text]
        grouped[row.get("evaluation_slice", "UNKNOWN")].append(bool(matches))
        if matches and len(examples) < 20:
            examples.append({"query_id": row["query_id"], "skill_ids": matches})
    return {
        "overall_rate": sum(
            map(bool, (item for values in grouped.values() for item in values))
        )
        / max(sum(map(len, grouped.values())), 1),
        "by_slice": {
            key: sum(values) / len(values) for key, values in sorted(grouped.items())
        },
        "examples": examples,
    }


def corpus_overlap_statistics(rows, skills, condition, ngram_size: int = 4):
    _, texts = build_skill_corpus(skills, condition)
    corpus_lines = {
        " ".join(line.casefold().split())
        for text in texts
        for line in text.splitlines()
        if line.strip()
    }
    skill_ngrams = [_ngrams(text, ngram_size) for text in texts]
    exact = 0
    overlaps = []
    by_slice: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        query = " ".join(row["text"].casefold().split())
        exact += int(any(line in query for line in corpus_lines))
        query_ngrams = _ngrams(query, ngram_size)
        value = max(
            (
                len(query_ngrams & item) / max(len(query_ngrams | item), 1)
                for item in skill_ngrams
            ),
            default=0.0,
        )
        overlaps.append(value)
        by_slice[row.get("evaluation_slice", "UNKNOWN")].append(value)
    return {
        "condition": condition,
        "complete_line_subsequence_rate": exact / max(len(rows), 1),
        "char_ngram_jaccard": _distribution(overlaps),
        "by_slice_mean": {
            key: statistics.fmean(values) for key, values in sorted(by_slice.items())
        },
    }


def _wrapper_only_classifier(train_rows, rows):
    counts: defaultdict[str, Counter] = defaultdict(Counter)
    for row in train_rows:
        counts[_wrapper(row)]["known" if row.get("known") else "unknown"] += 1
    global_rate = sum(row.get("known", False) for row in train_rows) / len(train_rows)
    scores = []
    labels = []
    for row in rows:
        counter = counts[_wrapper(row)]
        scores.append((counter["known"] + global_rate) / (sum(counter.values()) + 1))
        labels.append(int(bool(row.get("known"))))
    return {"auroc": _auroc(labels, scores), "feature_count": len(counts)}


def _shape_only_classifier(train_rows, rows):
    known = [_shape(row["text"]) for row in train_rows if row.get("known")]
    unknown = [_shape(row["text"]) for row in train_rows if not row.get("known")]
    known_mean = _means(known)
    unknown_mean = _means(unknown)
    variances = [
        statistics.pvariance([item[index] for item in known + unknown]) + 1e-6
        for index in range(4)
    ]
    weights = [
        (known_mean[index] - unknown_mean[index]) / variances[index]
        for index in range(4)
    ]
    scores = [
        sum(a * b for a, b in zip(_shape(row["text"]), weights, strict=True))
        for row in rows
    ]
    labels = [int(bool(row.get("known"))) for row in rows]
    return {
        "auroc": _auroc(labels, scores),
        "features": ("length", "punctuation", "sentence_count", "line_count"),
    }


def _wrapper(row):
    folded = row["text"].casefold()
    for language, values in NEUTRAL_WRAPPERS.items():
        for index, value in enumerate(values):
            if value.casefold() in folded:
                return f"{language}:{index}"
    return "none"


def _shape(text):
    return (
        float(len(text)),
        float(sum(text.count(mark) for mark in ".,;:!?-/")),
        float(sum(text.count(mark) for mark in ".!?")),
        float(text.count("\n") + 1),
    )


def _means(rows):
    return [statistics.fmean(item[index] for item in rows) for index in range(4)]


def _ngrams(text, size):
    value = " ".join(text.casefold().split())
    return {
        value[index : index + size] for index in range(max(len(value) - size + 1, 1))
    }


def _distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"mean": 0.0, "p50": 0.0, "p90": 0.0, "max": 0.0}
    return {
        "mean": statistics.fmean(ordered),
        "p50": ordered[len(ordered) // 2],
        "p90": ordered[min(len(ordered) - 1, math.floor(len(ordered) * 0.9))],
        "max": ordered[-1],
    }


def _auroc(labels, scores):
    pairs = sorted(zip(scores, labels, strict=True))
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return 0.0
    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2
        rank_sum += average_rank * sum(label for _, label in pairs[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)
