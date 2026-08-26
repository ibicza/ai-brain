"""Small deterministic assistive route baselines."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any


class CharacterNgramRouter:
    def __init__(self, *, n: int = 3) -> None:
        self.n = n
        self.profiles: dict[str, Counter[str]] = {}

    def fit(self, rows: list[dict[str, Any]]) -> CharacterNgramRouter:
        profiles: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            profiles[row["label"]].update(_ngrams(row["text"], self.n))
        self.profiles = dict(profiles)
        return self

    def scores(self, text: str) -> dict[str, float]:
        query = Counter(_ngrams(text, self.n))
        return {
            label: _cosine(query, profile) for label, profile in self.profiles.items()
        }

    def predict(self, text: str) -> str:
        scores = self.scores(text)
        return max(scores, key=lambda label: (scores[label], label))


class TokenOverlapRouter(CharacterNgramRouter):
    def __init__(self) -> None:
        super().__init__(n=0)

    def fit(self, rows: list[dict[str, Any]]) -> TokenOverlapRouter:
        profiles: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            profiles[row["label"]].update(_tokens(row["text"]))
        self.profiles = dict(profiles)
        return self

    def scores(self, text: str) -> dict[str, float]:
        query = Counter(_tokens(text))
        return {
            label: _cosine(query, profile) for label, profile in self.profiles.items()
        }


def _ngrams(text: str, n: int) -> tuple[str, ...]:
    normalized = " ".join(text.casefold().split())
    return tuple(
        normalized[index : index + n]
        for index in range(max(0, len(normalized) - n + 1))
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", text.casefold()))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    numerator = sum(value * right.get(key, 0) for key, value in left.items())
    denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    return numerator / denominator if denominator else 0.0
