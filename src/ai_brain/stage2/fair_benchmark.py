"""Deterministic retrieval baselines for the M-25.1 fair benchmark."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from typing import Any

from ai_brain.stage2.models import SkillRecord
from ai_brain.stage2.skill_corpora import build_skill_corpus

BASELINES = (
    "lexical_token_overlap",
    "bm25",
    "character_ngram",
    "exact_catalog_substring",
    "minimal_structured_feature",
    "random",
)
_TOKEN = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


def evaluate_fair_deterministic_baselines(
    skills: list[SkillRecord], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    skill_ids, rich = build_skill_corpus(skills, "rich")
    _, minimal = build_skill_corpus(skills, "minimal")
    corpora = {"rich": rich, "minimal": minimal}
    return {
        baseline: _evaluate(baseline, skill_ids, corpora, rows)
        for baseline in BASELINES
    }


def _evaluate(baseline, skill_ids, corpora, rows):
    target_index = {skill_id: index for index, skill_id in enumerate(skill_ids)}
    corpus = corpora["minimal" if baseline == "minimal_structured_feature" else "rich"]
    tokenized = [Counter(_tokens(text)) for text in corpus]
    ngrams = [_ngrams(text) for text in corpus]
    document_frequency = Counter(token for values in tokenized for token in set(values))
    average_length = sum(sum(values.values()) for values in tokenized) / len(tokenized)
    scored = []
    for row in rows:
        query = row["text"]
        if baseline == "random":
            digest = hashlib.sha256(query.encode("utf-8")).digest()
            first = int.from_bytes(digest[:8], "big") % len(skill_ids)
            ranking = [first] + [
                index for index in range(len(skill_ids)) if index != first
            ]
            scores = [0.0] * len(skill_ids)
            scores[first] = 1.0
        else:
            scores = _scores(
                baseline,
                query,
                corpus,
                tokenized,
                ngrams,
                document_frequency,
                average_length,
            )
            ranking = sorted(
                range(len(skill_ids)),
                key=lambda index: (-scores[index], skill_ids[index]),
            )
        target = target_index.get(row.get("target_skill_id"))
        neighbor = target_index.get(row.get("neighbor_skill_id"))
        rank = ranking.index(target) + 1 if target is not None else 0
        scored.append(
            {
                "slice": row.get("evaluation_slice", "UNKNOWN"),
                "known": target is not None,
                "rank": rank,
                "target_score": scores[target] if target is not None else None,
                "neighbor_score": scores[neighbor] if neighbor is not None else None,
                "hard": bool(row.get("neighbor_skill_id")),
            }
        )
    known = [item for item in scored if item["known"]]
    by_slice: defaultdict[str, list[dict]] = defaultdict(list)
    for item in known:
        by_slice[item["slice"]].append(item)
    hard = [item for item in known if item["hard"]]
    pairwise = [
        item["target_score"] > item["neighbor_score"]
        for item in hard
        if item["neighbor_score"] is not None
    ]
    return {
        **_rank_metrics(known),
        "known_count": len(known),
        "by_slice": {
            key: {**_rank_metrics(values), "count": len(values)}
            for key, values in sorted(by_slice.items())
        },
        "hard_neighbor_pairwise": sum(pairwise) / len(pairwise) if pairwise else 0.0,
        "trusted_selector": False,
    }


def _scores(
    baseline, query, corpus, tokenized, ngrams, document_frequency, average_length
):
    query_tokens = Counter(_tokens(query))
    if baseline in {"lexical_token_overlap", "minimal_structured_feature"}:
        query_set = set(query_tokens)
        return [
            len(query_set & set(item)) / max(len(query_set | set(item)), 1)
            for item in tokenized
        ]
    if baseline == "character_ngram":
        query_set = _ngrams(query)
        return [
            len(query_set & item) / max(len(query_set | item), 1) for item in ngrams
        ]
    if baseline == "exact_catalog_substring":
        folded = " ".join(query.casefold().split())
        return [
            float(
                any(
                    " ".join(line.casefold().split()) in folded
                    for line in text.splitlines()
                    if line.strip()
                )
            )
            for text in corpus
        ]
    result = []
    for document in tokenized:
        length = sum(document.values())
        score = 0.0
        for token in query_tokens:
            frequency = document[token]
            if not frequency:
                continue
            inverse = math.log(
                1
                + (len(tokenized) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.5 * (
                0.25 + 0.75 * length / max(average_length, 1)
            )
            score += inverse * frequency * 2.5 / denominator
        result.append(score)
    return result


def _rank_metrics(rows):
    if not rows:
        return {"top1": 0.0, "top3": 0.0, "top5": 0.0, "mrr": 0.0}
    return {
        "top1": sum(item["rank"] <= 1 for item in rows) / len(rows),
        "top3": sum(item["rank"] <= 3 for item in rows) / len(rows),
        "top5": sum(item["rank"] <= 5 for item in rows) / len(rows),
        "mrr": sum(1 / item["rank"] for item in rows) / len(rows),
    }


def _tokens(text):
    return _TOKEN.findall(text.casefold())


def _ngrams(text, size=3):
    value = " ".join(text.casefold().split())
    return {
        value[index : index + size] for index in range(max(len(value) - size + 1, 1))
    }
