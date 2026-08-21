"""Lightweight learned structured ranking utilities."""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from ai_brain.rules.ast import ProgramAst, render_canonical_program
from ai_brain.rules.specifications import ProgramSpecification


def tokenize(text: str) -> list[str]:
    return [part.lower() for part in text.replace("(", " ").replace(")", " ").split()]


def feature_counter(spec: ProgramSpecification, program: ProgramAst) -> Counter[str]:
    spec_tokens = tokenize(spec.to_model_text())
    program_tokens = tokenize(render_canonical_program(program))
    features: Counter[str] = Counter()
    for token in spec_tokens:
        features[f"s:{token}"] += 1
    for token in program_tokens:
        features[f"p:{token}"] += 1
    for token in set(spec_tokens) & set(program_tokens):
        features[f"x:{token}"] += 1
    features[f"transfers:{len(spec.transfers)}"] += 1
    features[f"drops:{len(spec.drops)}"] += 1
    return features


@dataclass
class StructuredPerceptronRanker:
    vocab: dict[str, int]
    weights: list[float]
    seed: int = 0

    @classmethod
    def train(
        cls,
        rows: Sequence[tuple[ProgramSpecification, ProgramAst, int]],
        *,
        seed: int = 0,
        epochs: int = 4,
        lr: float = 0.1,
    ) -> StructuredPerceptronRanker:
        vocab: dict[str, int] = {}
        for spec, program, _label in rows:
            for feature in feature_counter(spec, program):
                if feature not in vocab:
                    vocab[feature] = len(vocab)
        weights = [0.0] * len(vocab)
        rng = random.Random(seed)
        work = list(rows)
        for _ in range(epochs):
            rng.shuffle(work)
            for spec, program, label in work:
                score = sum(
                    weights[vocab[key]] * value
                    for key, value in feature_counter(spec, program).items()
                    if key in vocab
                )
                pred = 1 if score >= 0 else 0
                error = label - pred
                if error:
                    for key, value in feature_counter(spec, program).items():
                        if key in vocab:
                            weights[vocab[key]] += lr * error * value
        return cls(vocab, weights, seed)

    @property
    def parameter_count(self) -> int:
        return len(self.weights)

    def score(self, spec: ProgramSpecification, program: ProgramAst) -> float:
        return sum(
            self.weights[self.vocab[key]] * value
            for key, value in feature_counter(spec, program).items()
            if key in self.vocab
        )


def pairwise_auc(scores: Sequence[tuple[float, int]]) -> float:
    positives = [score for score, label in scores if label]
    negatives = [score for score, label in scores if not label]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += float(positive > negative) + 0.5 * float(positive == negative)
    return wins / (len(positives) * len(negatives))


def cosine(left: Counter[str], right: Counter[str]) -> float:
    dot = sum(value * right[key] for key, value in left.items())
    norm_l = math.sqrt(sum(value * value for value in left.values()))
    norm_r = math.sqrt(sum(value * value for value in right.values()))
    return dot / max(1e-9, norm_l * norm_r)
