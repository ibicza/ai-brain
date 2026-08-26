"""Train, freeze, and open the M-25 research-only learned retriever."""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage1.models import content_hash, utc_now
from ai_brain.stage2.dataset import load_jsonl, verify_blind_freeze
from ai_brain.stage2.learned import (
    BiEncoderConfig,
    evaluate_cross_language_consistency,
    evaluate_retriever,
    load_retriever,
    save_retriever,
    train_bi_encoder,
)
from ai_brain.stage2.registry import SkillRegistry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = ROOT / "artifacts" / "stage2" / "m25"
DEFAULT_RUNS = ROOT / "runs" / "m25_learned"


def train_seed(
    registry_path: Path,
    dataset_dir: Path,
    output_dir: Path,
    config: BiEncoderConfig,
    *,
    device: str | None,
) -> dict[str, Any]:
    verify_blind_freeze(dataset_dir)
    registry = SkillRegistry.load(registry_path)
    retriever, training = train_bi_encoder(
        registry,
        load_jsonl(dataset_dir / "train.jsonl"),
        load_jsonl(dataset_dir / "calibration.jsonl"),
        config=config,
        device=device,
    )
    validation = evaluate_retriever(
        retriever, load_jsonl(dataset_dir / "validation.jsonl")
    )
    development = evaluate_retriever(
        retriever, load_jsonl(dataset_dir / "development.jsonl")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / f"seed_{config.seed}.pt"
    save_retriever(retriever, checkpoint, training)
    result = {
        "seed": config.seed,
        "config": asdict(config),
        "training": training,
        "validation": validation,
        "development": development,
        "checkpoint": checkpoint.name,
        "blind_opened": False,
    }
    _write_json(output_dir / f"seed_{config.seed}_development.json", result)
    return result


def freeze_recipe(
    dataset_dir: Path,
    output_dir: Path,
    seeds: list[int],
    config: BiEncoderConfig,
) -> dict[str, Any]:
    verify_blind_freeze(dataset_dir)
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    development = [
        json.loads(
            (output_dir / f"seed_{seed}_development.json").read_text(encoding="utf-8")
        )
        for seed in seeds
    ]
    first = development[0]["development"]
    multi_seed_eligible = (
        first["top5"] >= 0.98
        and first["hard_neighbor"]["top1"] >= 0.85
        and first["abstention"]["false_known_rate"] <= 0.05
    )
    if len(seeds) > 1 and not multi_seed_eligible:
        raise ValueError("Development gates do not permit multi-seed confirmation")
    recipe = {
        "schema_version": 1,
        "recipe": "hashed_char_ngram_bilingual_bi_encoder",
        "config": asdict(config),
        "confirmed_seeds": seeds,
        "multi_seed_eligible": multi_seed_eligible,
        "blind_public_sha256": manifest["blind_public_sha256"],
        "blind_targets_sha256": manifest["blind_targets_sha256"],
        "development_result_hashes": [content_hash(item) for item in development],
        "frozen_at": utc_now(),
    }
    recipe["recipe_hash"] = content_hash(recipe)
    _write_json(output_dir / "recipe_freeze.json", recipe)
    return recipe


def open_blind(
    registry_path: Path, dataset_dir: Path, output_dir: Path
) -> dict[str, Any]:
    verify_blind_freeze(dataset_dir)
    if (output_dir / "blind_final.json").exists():
        raise ValueError("Blind final has already been opened")
    recipe = json.loads((output_dir / "recipe_freeze.json").read_text(encoding="utf-8"))
    expected_hash = recipe.pop("recipe_hash")
    if content_hash(recipe) != expected_hash:
        raise ValueError("Recipe freeze hash mismatch")
    recipe["recipe_hash"] = expected_hash
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    if (
        recipe["blind_public_sha256"] != manifest["blind_public_sha256"]
        or recipe["blind_targets_sha256"] != manifest["blind_targets_sha256"]
    ):
        raise ValueError("Blind artifacts differ from the frozen recipe")
    registry = SkillRegistry.load(registry_path)
    public = load_jsonl(dataset_dir / "blind.jsonl")
    targets = {
        row["query_id"]: row
        for row in load_jsonl(dataset_dir / "blind_targets.hidden.jsonl")
    }
    blind_rows = [{**row, **targets[row["query_id"]]} for row in public]
    seed_results = []
    for seed in recipe["confirmed_seeds"]:
        retriever = load_retriever(
            output_dir / f"seed_{seed}.pt", allow_archival_research=True
        )
        if retriever.registry_hash != registry.manifest.registry_hash:
            raise ValueError("Checkpoint registry hash mismatch")
        seed_results.append(
            {"seed": seed, "metrics": evaluate_retriever(retriever, blind_rows)}
        )
    result = {
        "recipe_hash": recipe["recipe_hash"],
        "opened_once_at": utc_now(),
        "seed_results": seed_results,
        "summary": _multi_seed_summary(seed_results),
    }
    _write_json(output_dir / "blind_final.json", result)
    return result


def verify_evidence(
    registry_path: Path, dataset_dir: Path, output_dir: Path
) -> dict[str, Any]:
    verify_blind_freeze(dataset_dir)
    registry = SkillRegistry.load(registry_path)
    recipe = json.loads((output_dir / "recipe_freeze.json").read_text(encoding="utf-8"))
    declared_recipe_hash = recipe.pop("recipe_hash")
    if content_hash(recipe) != declared_recipe_hash:
        raise ValueError("Recipe freeze hash mismatch")
    blind = json.loads((output_dir / "blind_final.json").read_text(encoding="utf-8"))
    if blind["recipe_hash"] != declared_recipe_hash:
        raise ValueError("Blind result belongs to another recipe")
    if [item["seed"] for item in blind["seed_results"]] != recipe["confirmed_seeds"]:
        raise ValueError("Blind result seed set mismatch")
    cross_language = {}
    for seed in recipe["confirmed_seeds"]:
        retriever = load_retriever(
            output_dir / f"seed_{seed}.pt", allow_archival_research=True
        )
        if retriever.registry_hash != registry.manifest.registry_hash:
            raise ValueError("Checkpoint registry hash mismatch")
        cross_language[str(seed)] = evaluate_cross_language_consistency(
            retriever, registry
        )
    result = {
        "status": "VALID",
        "recipe_hash": declared_recipe_hash,
        "confirmed_seeds": recipe["confirmed_seeds"],
        "cross_language": cross_language,
        "verified_at": utc_now(),
    }
    _write_json(output_dir / "evidence_verification.json", result)
    return result


def _multi_seed_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    paths = {
        "top1": lambda item: item["metrics"]["top1"],
        "top5": lambda item: item["metrics"]["top5"],
        "hard_neighbor_top1": lambda item: item["metrics"]["hard_neighbor"]["top1"],
        "unknown_abstention": lambda item: item["metrics"]["abstention"][
            "unknown_abstention"
        ],
        "false_known_rate": lambda item: item["metrics"]["abstention"][
            "false_known_rate"
        ],
    }
    summary = {}
    for name, accessor in paths.items():
        values = [accessor(item) for item in results]
        summary[name] = {
            "mean": statistics.fmean(values),
            "std": statistics.pstdev(values),
            "min": min(values),
            "max": max(values),
        }
    return summary


def _config(arguments) -> BiEncoderConfig:
    return BiEncoderConfig(
        feature_count=arguments.feature_count,
        hidden_size=arguments.hidden_size,
        embedding_size=arguments.embedding_size,
        learning_rate=arguments.learning_rate,
        temperature=arguments.temperature,
        batch_size=arguments.batch_size,
        steps=arguments.steps,
        seed=arguments.seed,
        false_known_bound=arguments.false_known_bound,
    )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("train", "freeze", "blind", "verify"))
    parser.add_argument(
        "--registry", type=Path, default=DEFAULT_ARTIFACTS / "skill_registry.json"
    )
    parser.add_argument(
        "--dataset-dir", type=Path, default=DEFAULT_ARTIFACTS / "queries"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--seed", type=int, default=25_101)
    parser.add_argument("--seeds", default="25101")
    parser.add_argument("--device")
    parser.add_argument("--feature-count", type=int, default=4096)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--embedding-size", type=int, default=96)
    parser.add_argument("--learning-rate", type=float, default=2e-3)
    parser.add_argument("--temperature", type=float, default=0.08)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--steps", type=int, default=1500)
    parser.add_argument("--false-known-bound", type=float, default=0.02)
    arguments = parser.parse_args()
    config = _config(arguments)
    if arguments.command == "train":
        result = train_seed(
            arguments.registry,
            arguments.dataset_dir,
            arguments.output_dir,
            config,
            device=arguments.device,
        )
    elif arguments.command == "freeze":
        result = freeze_recipe(
            arguments.dataset_dir,
            arguments.output_dir,
            [int(item) for item in arguments.seeds.split(",")],
            config,
        )
    elif arguments.command == "blind":
        result = open_blind(
            arguments.registry, arguments.dataset_dir, arguments.output_dir
        )
    else:
        result = verify_evidence(
            arguments.registry, arguments.dataset_dir, arguments.output_dir
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
