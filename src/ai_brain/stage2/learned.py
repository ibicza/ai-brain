"""Research-only hashed-text bi-encoder for assistive skill ranking.

This module is deliberately absent from ``ai_brain.stage2`` exports.  Importing the
trusted router therefore never imports torch, while experiments can opt in here.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn

from ai_brain.stage1.models import content_hash, utc_now
from ai_brain.stage2.dataset import load_jsonl, model_visible_text
from ai_brain.stage2.models import SkillRecord
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage2.skill_corpora import build_skill_corpus


@dataclass(frozen=True)
class BiEncoderConfig:
    feature_count: int = 4096
    hidden_size: int = 128
    embedding_size: int = 96
    learning_rate: float = 2e-3
    temperature: float = 0.08
    batch_size: int = 128
    steps: int = 1500
    seed: int = 25_101
    false_known_bound: float = 0.02
    corpus_condition: str = "rich"
    hard_negative_weight: float = 0.0
    hard_negative_margin: float = 0.15
    explicit_semantic_features: bool = False


class SkillBiEncoder(nn.Module):
    def __init__(self, config: BiEncoderConfig) -> None:
        super().__init__()
        self.config = config
        self.query_encoder = _TextEncoder(config)
        self.skill_encoder = _TextEncoder(config)

    def encode_queries(self, features: torch.Tensor) -> torch.Tensor:
        return self.query_encoder(features)

    def encode_skills(self, features: torch.Tensor) -> torch.Tensor:
        return self.skill_encoder(features)


class _TextEncoder(nn.Module):
    def __init__(self, config: BiEncoderConfig) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(config.feature_count, config.hidden_size),
            nn.GELU(),
            nn.Linear(config.hidden_size, config.embedding_size),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return nn.functional.normalize(self.layers(features), dim=-1)


@dataclass(frozen=True)
class LearnedRetriever:
    model: SkillBiEncoder
    config: BiEncoderConfig
    skill_ids: tuple[str, ...]
    skill_texts: tuple[str, ...]
    registry_hash: str
    threshold: float
    device: str

    @torch.inference_mode()
    def rank(
        self, text: str, language: str | None, *, top_k: int = 5
    ) -> dict[str, Any]:
        self.model.eval()
        query = _feature_tensor(
            [f"{language or 'unknown'}\n{text}"],
            self.config.feature_count,
            self.device,
            self.config.explicit_semantic_features,
        )
        skills = _feature_tensor(
            list(self.skill_texts),
            self.config.feature_count,
            self.device,
            self.config.explicit_semantic_features,
        )
        scores = (
            self.model.encode_queries(query)
            @ self.model.encode_skills(skills).transpose(0, 1)
        )[0]
        values, indices = torch.topk(scores, min(top_k, len(self.skill_ids)))
        ranked = [
            {"skill_id": self.skill_ids[index], "score": float(score), "rank": rank}
            for rank, (score, index) in enumerate(
                zip(values.tolist(), indices.tolist(), strict=True), 1
            )
        ]
        top_score = ranked[0]["score"] if ranked else float("-inf")
        return {
            "candidates": ranked,
            "known": top_score >= self.threshold,
            "threshold": self.threshold,
            "retrieval_mode": "LEARNED_BI_ENCODER_ASSISTIVE",
            "exact_match": False,
            "recommended_next_action": (
                "REVIEW_CANDIDATES" if top_score >= self.threshold else "RUN_SYNTHESIS"
            ),
        }


def train_bi_encoder(
    registry: SkillRegistry,
    train_rows: list[dict[str, Any]],
    calibration_rows: list[dict[str, Any]],
    *,
    config: BiEncoderConfig | None = None,
    device: str | None = None,
) -> tuple[LearnedRetriever, dict[str, Any]]:
    config = config or BiEncoderConfig()
    actual_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    _seed_everything(config.seed)
    skill_ids, skill_texts = _skill_corpus(registry, config.corpus_condition)
    skill_to_index = {skill_id: index for index, skill_id in enumerate(skill_ids)}
    known_rows = [
        row for row in train_rows if row.get("target_skill_id") in skill_to_index
    ]
    if not known_rows:
        raise ValueError("No known-skill training rows")
    model = SkillBiEncoder(config).to(actual_device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    skill_features = _feature_tensor(
        skill_texts,
        config.feature_count,
        actual_device,
        config.explicit_semantic_features,
    )
    train_features = _feature_tensor(
        [model_visible_text(row) for row in known_rows],
        config.feature_count,
        actual_device,
        config.explicit_semantic_features,
    )
    train_targets = torch.tensor(
        [skill_to_index[row["target_skill_id"]] for row in known_rows],
        dtype=torch.long,
        device=actual_device,
    )
    hard_targets = torch.tensor(
        [skill_to_index.get(row.get("neighbor_skill_id"), -1) for row in known_rows],
        dtype=torch.long,
        device=actual_device,
    )
    rng = random.Random(config.seed)
    losses: list[float] = []
    model.train()
    for step in range(config.steps):
        indices = torch.tensor(
            [rng.randrange(len(known_rows)) for _ in range(config.batch_size)],
            dtype=torch.long,
            device=actual_device,
        )
        query_features = train_features.index_select(0, indices)
        targets = train_targets.index_select(0, indices)
        query_embeddings = model.encode_queries(query_features)
        skill_embeddings = model.encode_skills(skill_features)
        logits = query_embeddings @ skill_embeddings.transpose(0, 1)
        loss = nn.functional.cross_entropy(logits / config.temperature, targets)
        selected_hard = hard_targets.index_select(0, indices)
        has_hard = selected_hard >= 0
        if config.hard_negative_weight and bool(has_hard.any()):
            rows = torch.arange(len(indices), device=actual_device)[has_hard]
            positive_scores = logits[rows, targets[has_hard]]
            negative_scores = logits[rows, selected_hard[has_hard]]
            hard_loss = nn.functional.relu(
                config.hard_negative_margin - positive_scores + negative_scores
            ).mean()
            loss = loss + config.hard_negative_weight * hard_loss
        if not torch.isfinite(loss):
            raise ValueError(f"Non-finite retriever loss at step {step}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        losses.append(float(loss.detach()))
    provisional = LearnedRetriever(
        model=model,
        config=config,
        skill_ids=skill_ids,
        skill_texts=skill_texts,
        registry_hash=registry.manifest.registry_hash,
        threshold=-1.0,
        device=actual_device,
    )
    threshold, calibration = calibrate_threshold(
        provisional,
        calibration_rows,
        false_known_bound=config.false_known_bound,
    )
    retriever = LearnedRetriever(
        model=model,
        config=config,
        skill_ids=skill_ids,
        skill_texts=skill_texts,
        registry_hash=registry.manifest.registry_hash,
        threshold=threshold,
        device=actual_device,
    )
    training = {
        "seed": config.seed,
        "device": actual_device,
        "steps": config.steps,
        "known_train_count": len(known_rows),
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "initial_loss": losses[0],
        "final_loss": losses[-1],
        "min_loss": min(losses),
        "threshold": threshold,
        "corpus_condition": config.corpus_condition,
        "hard_negative_weight": config.hard_negative_weight,
        "calibration": calibration,
    }
    return retriever, training


def calibrate_threshold(
    retriever: LearnedRetriever,
    rows: list[dict[str, Any]],
    *,
    false_known_bound: float = 0.05,
) -> tuple[float, dict[str, float]]:
    scored = _score_rows(retriever, rows)
    unknown_scores = sorted(
        item["score"] for item in scored if not item["known_target"]
    )
    if not unknown_scores:
        raise ValueError("Calibration split has no unknown queries")
    allowed = math.floor(false_known_bound * len(unknown_scores))
    descending = sorted(unknown_scores, reverse=True)
    threshold = (
        descending[allowed] + 1e-6
        if allowed < len(descending)
        else min(unknown_scores) - 1e-6
    )
    metrics = _abstention_metrics(scored, threshold)
    metrics["false_known_bound"] = false_known_bound
    return threshold, metrics


def evaluate_retriever(
    retriever: LearnedRetriever, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    scored = _score_rows(retriever, rows)
    known = [item for item in scored if item["known_target"]]
    unknown = [item for item in scored if not item["known_target"]]
    hard = [item for item in known if item["query_kind"] == "hard_neighbor"]
    ranks = [item["rank"] for item in known]
    by_language = {
        language: _ranking_metrics(
            [item for item in known if item["language"] == language]
        )
        for language in ("ru", "en")
    }
    return {
        **_ranking_metrics(known),
        "hard_neighbor": _ranking_metrics(hard),
        "known_count": len(known),
        "unknown_count": len(unknown),
        "mean_rank": sum(ranks) / len(ranks) if ranks else 0.0,
        "by_language": by_language,
        "language_top1_gap": abs(by_language["ru"]["top1"] - by_language["en"]["top1"]),
        "abstention": _abstention_metrics(scored, retriever.threshold),
        "failure_samples": [
            {
                "query_id": item["query_id"],
                "target": item["target"],
                "prediction": item["prediction"],
                "score": item["score"],
                "rank": item["rank"],
            }
            for item in scored
            if item["known_target"] and item["rank"] != 1
        ][:20],
    }


def evaluate_cross_language_consistency(
    retriever: LearnedRetriever, registry: SkillRegistry
) -> dict[str, float]:
    skills = sorted(registry.active_records(), key=lambda item: item.skill_id)
    retriever.model.eval()
    skill_features = _feature_tensor(
        list(retriever.skill_texts),
        retriever.config.feature_count,
        retriever.device,
        retriever.config.explicit_semantic_features,
    )
    with torch.inference_mode():
        skill_embeddings = retriever.model.encode_skills(skill_features)
    rankings = {}
    latencies = {}
    for language in ("ru", "en"):
        texts = [
            f"{language}\n{skill.aliases_ru[0] if language == 'ru' else skill.aliases_en[0]}"
            for skill in skills
        ]
        started = time.perf_counter()
        features = _feature_tensor(
            texts,
            retriever.config.feature_count,
            retriever.device,
            retriever.config.explicit_semantic_features,
        )
        with torch.inference_mode():
            scores = retriever.model.encode_queries(features) @ skill_embeddings.T
            rankings[language] = torch.topk(scores, 5, dim=1).indices.cpu().tolist()
        latencies[language] = (time.perf_counter() - started) * 1000 / len(skills)
    top1_equal = 0
    top1_target = 0
    full_ranking_equal = 0
    overlaps = []
    for expected, (ru_ranking, en_ranking) in enumerate(
        zip(rankings["ru"], rankings["en"], strict=True)
    ):
        top1_equal += int(ru_ranking[0] == en_ranking[0])
        top1_target += int(ru_ranking[0] == en_ranking[0] == expected)
        full_ranking_equal += int(ru_ranking == en_ranking)
        overlaps.append(
            len(set(ru_ranking) & set(en_ranking))
            / len(set(ru_ranking) | set(en_ranking))
        )
    pairs = len(skills)
    return {
        "pair_count": float(pairs),
        "top1_skill_equality": top1_equal / pairs,
        "top1_target_accuracy": top1_target / pairs,
        "top5_ranking_equality": full_ranking_equal / pairs,
        "top5_jaccard_overlap": statistics.fmean(overlaps),
        "ru_latency_ms": latencies["ru"],
        "en_latency_ms": latencies["en"],
    }


def save_retriever(
    retriever: LearnedRetriever, path: Path, training: dict[str, Any]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "schema_version": 1,
            "config": asdict(retriever.config),
            "state_dict": retriever.model.state_dict(),
            "skill_ids": retriever.skill_ids,
            "skill_texts": retriever.skill_texts,
            "registry_hash": retriever.registry_hash,
            "threshold": retriever.threshold,
            "training": training,
            "created_at": utc_now(),
        },
        path,
    )


def load_retriever(path: Path, *, device: str = "cpu") -> LearnedRetriever:
    payload = torch.load(path, map_location=device, weights_only=False)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported learned retriever checkpoint")
    config = BiEncoderConfig(**payload["config"])
    model = SkillBiEncoder(config).to(device)
    model.load_state_dict(payload["state_dict"], strict=True)
    return LearnedRetriever(
        model=model,
        config=config,
        skill_ids=tuple(payload["skill_ids"]),
        skill_texts=tuple(payload["skill_texts"]),
        registry_hash=payload["registry_hash"],
        threshold=float(payload["threshold"]),
        device=device,
    )


def train_from_directory(
    registry: SkillRegistry,
    dataset_dir: Path,
    output_path: Path,
    *,
    config: BiEncoderConfig | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    config = config or BiEncoderConfig()
    retriever, training = train_bi_encoder(
        registry,
        load_jsonl(dataset_dir / "train.jsonl"),
        load_jsonl(dataset_dir / "calibration.jsonl"),
        config=config,
        device=device,
    )
    save_retriever(retriever, output_path, training)
    development = evaluate_retriever(
        retriever, load_jsonl(dataset_dir / "development.jsonl")
    )
    return {"training": training, "development": development}


def _score_rows(
    retriever: LearnedRetriever, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    retriever.model.eval()
    skill_features = _feature_tensor(
        list(retriever.skill_texts),
        retriever.config.feature_count,
        retriever.device,
        retriever.config.explicit_semantic_features,
    )
    with torch.inference_mode():
        skill_embeddings = retriever.model.encode_skills(skill_features)
    skill_to_index = {
        skill_id: index for index, skill_id in enumerate(retriever.skill_ids)
    }
    scored: list[dict[str, Any]] = []
    for start in range(0, len(rows), 512):
        batch = rows[start : start + 512]
        features = _feature_tensor(
            [model_visible_text(row) for row in batch],
            retriever.config.feature_count,
            retriever.device,
            retriever.config.explicit_semantic_features,
        )
        with torch.inference_mode():
            scores = retriever.model.encode_queries(features) @ skill_embeddings.T
        order = torch.argsort(scores, dim=1, descending=True).cpu()
        max_scores = scores.max(dim=1).values.cpu().tolist()
        for batch_index, (row, ranking, score) in enumerate(
            zip(batch, order, max_scores, strict=True)
        ):
            target = row.get("target_skill_id")
            target_index = skill_to_index.get(target)
            rank = (
                int((ranking == target_index).nonzero(as_tuple=False)[0].item()) + 1
                if target_index is not None
                else 0
            )
            neighbor_index = skill_to_index.get(row.get("neighbor_skill_id"))
            scored.append(
                {
                    "query_id": row["query_id"],
                    "language": row["language"],
                    "query_kind": row.get("query_kind", "blind"),
                    "known_target": target_index is not None,
                    "target": target,
                    "prediction": retriever.skill_ids[int(ranking[0])],
                    "rank": rank,
                    "score": float(score),
                    "target_score": (
                        float(scores[batch_index, target_index])
                        if target_index is not None
                        else None
                    ),
                    "neighbor_score": (
                        float(scores[batch_index, neighbor_index])
                        if neighbor_index is not None
                        else None
                    ),
                    "evaluation_slice": row.get("evaluation_slice", "UNKNOWN"),
                    "ambiguous": bool(row.get("ambiguous", False)),
                    "unknown_family": row.get("unknown_family"),
                    "changed_field": row.get("changed_field"),
                    "query_pair_id": row.get("query_pair_id"),
                }
            )
    return scored


def _ranking_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    count = len(rows)
    if not count:
        return {"top1": 0.0, "top3": 0.0, "top5": 0.0, "mrr": 0.0}
    return {
        "top1": sum(item["rank"] <= 1 for item in rows) / count,
        "top3": sum(item["rank"] <= 3 for item in rows) / count,
        "top5": sum(item["rank"] <= 5 for item in rows) / count,
        "mrr": sum(1.0 / item["rank"] for item in rows) / count,
    }


def _abstention_metrics(
    rows: list[dict[str, Any]], threshold: float
) -> dict[str, float]:
    known = [item for item in rows if item["known_target"]]
    unknown = [item for item in rows if not item["known_target"]]
    known_recall = (
        sum(item["score"] >= threshold for item in known) / len(known) if known else 0.0
    )
    unknown_abstention = (
        sum(item["score"] < threshold for item in unknown) / len(unknown)
        if unknown
        else 0.0
    )
    labels = [int(item["known_target"]) for item in rows]
    scores = [item["score"] for item in rows]
    return {
        "threshold": threshold,
        "known_recall": known_recall,
        "unknown_abstention": unknown_abstention,
        "false_known_rate": 1.0 - unknown_abstention,
        "false_unknown_rate": 1.0 - known_recall,
        "auroc": _auroc(labels, scores),
        "auprc": _auprc(labels, scores),
        "risk_at_80_coverage": _risk_at_coverage(rows, 0.8),
    }


def _auroc(labels: list[int], scores: list[float]) -> float:
    positives = [score for label, score in zip(labels, scores, strict=True) if label]
    negatives = [
        score for label, score in zip(labels, scores, strict=True) if not label
    ]
    if not positives or not negatives:
        return 0.0
    wins = sum(
        1.0 if positive > negative else 0.5 if positive == negative else 0.0
        for positive in positives
        for negative in negatives
    )
    return wins / (len(positives) * len(negatives))


def _auprc(labels: list[int], scores: list[float]) -> float:
    positives = sum(labels)
    if positives == 0:
        return 0.0
    ranked = sorted(zip(scores, labels, strict=True), reverse=True)
    true_positives = 0
    precision_sum = 0.0
    for rank, (_, label) in enumerate(ranked, 1):
        if label:
            true_positives += 1
            precision_sum += true_positives / rank
    return precision_sum / positives


def _risk_at_coverage(rows: list[dict[str, Any]], coverage: float) -> float:
    known = sorted(
        (item for item in rows if item["known_target"]),
        key=lambda item: item["score"],
        reverse=True,
    )
    selected = known[: math.ceil(len(known) * coverage)]
    return (
        sum(item["rank"] != 1 for item in selected) / len(selected) if selected else 0.0
    )


def _skill_corpus(
    registry: SkillRegistry, condition: str = "rich"
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return build_skill_corpus(registry.active_records(), condition)


def _skill_text(skill: SkillRecord) -> str:
    # IDs are labels only and are deliberately excluded from encoder input.
    fields = (
        skill.canonical_name_ru,
        skill.canonical_name_en,
        skill.effect_summary,
        *skill.aliases_ru,
        *skill.aliases_en,
        *skill.controlled_examples_ru,
        *skill.controlled_examples_en,
        json.dumps(skill.effect_schema, ensure_ascii=False, sort_keys=True),
    )
    text = "\n".join(fields)
    if skill.skill_id in text or skill.rule_id in text:
        raise ValueError("Skill encoder text contains a hidden identifier")
    return text


def _feature_tensor(
    texts: list[str] | tuple[str, ...],
    size: int,
    device: str,
    explicit_semantic_features: bool = False,
):
    matrix = torch.zeros((len(texts), size), dtype=torch.float32)
    for row, text in enumerate(texts):
        counts = Counter(_hashed_features(text, size, explicit_semantic_features))
        for column, count in counts.items():
            matrix[row, column] = 1.0 + math.log(count)
    return nn.functional.normalize(matrix, dim=1).to(device)


def _hashed_features(text: str, size: int, explicit_semantic_features: bool = False):
    folded = " ".join(text.casefold().split())
    padded = f"^{folded}$"
    for width in (2, 3, 4, 5):
        for index in range(max(0, len(padded) - width + 1)):
            feature = padded[index : index + width].encode("utf-8")
            yield (
                int.from_bytes(hashlib.blake2b(feature, digest_size=8).digest(), "big")
                % size
            )
    for token in folded.split():
        yield (
            int.from_bytes(
                hashlib.blake2b(f"w:{token}".encode(), digest_size=8).digest(),
                "big",
            )
            % size
        )
    if explicit_semantic_features:
        for semantic in _explicit_semantic_features(folded):
            column = (
                int.from_bytes(
                    hashlib.blake2b(
                        f"semantic:{semantic}".encode(), digest_size=8
                    ).digest(),
                    "big",
                )
                % size
            )
            for _ in range(8):
                yield column


def _explicit_semantic_features(folded: str) -> tuple[str, ...]:
    features: list[str] = []
    lexemes = {
        "MOVE": (
            "relocate",
            "route",
            "send",
            "направь",
            "передай",
            "отправь",
            "move",
            "convey",
            "перенеси",
            "переправь",
            "move_one",
        ),
        "DROP": (
            "discard",
            "remove",
            "empty",
            "удали",
            "опустоши",
            "убери",
            "clear",
            "purge",
            "очисти",
            "ликвидируй",
            "drop_one",
        ),
        "HALT": (
            "finish",
            "end",
            "halt",
            "заверши",
            "прекрати",
            "закончи",
        ),
    }
    for operation, values in lexemes.items():
        if any(value in folded for value in values):
            features.append(f"OP:{operation}")

    actions = re.findall(r"(move_one|drop_one)\(([a-d]),([a-d]|none)\)", folded)
    for index, (action, source, destination) in enumerate(actions):
        features.extend((f"PHASE:{index}:{action}", f"SRC:{index}:{source}"))
        if destination != "none":
            features.append(f"DEST:{destination}")

    move_match = re.search(r"\bfrom\s+(.+?)\s+(?:to|into)\s+([a-d])\b", folded)
    if move_match is None:
        move_match = re.search(r"\bиз\s+(.+?)\s+в\s+([a-d])\b", folded)
    if move_match is not None:
        sources = re.findall(r"\b([a-d])\b", move_match.group(1))
        for index, source in enumerate(sources):
            features.append(f"SRC:{index}:{source}")
        features.append(f"DEST:{move_match.group(2)}")

    drop_match = re.search(
        r"(?:discard|remove|empty|clear|purge|удали|опустоши|убери|очисти|ликвидируй)"
        r"\s+(?:every\s+unit\s+from\s+|все\s+единицы\s+из\s+)?([a-d])\b",
        folded,
    )
    if drop_match is not None:
        features.append(f"DROP_SRC:{drop_match.group(1)}")
    for role in re.findall(r"\b([a-d])\b", folded):
        features.append(f"ROLE:{role}")
    return tuple(features)


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def experiment_hash(config: BiEncoderConfig, registry_hash: str) -> str:
    return content_hash({"config": asdict(config), "registry_hash": registry_hash})
