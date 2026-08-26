"""Train, freeze, open once, and verify the M-25.1 fair retriever."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage1.models import content_hash, utc_now
from ai_brain.stage2.dataset import load_jsonl
from ai_brain.stage2.fair_benchmark import evaluate_fair_deterministic_baselines
from ai_brain.stage2.fair_dataset import load_fair_blind, verify_fair_blind_freeze
from ai_brain.stage2.fair_diagnostics import diagnose_label_leakage
from ai_brain.stage2.fair_evaluation import evaluate_fair_retriever
from ai_brain.stage2.learned import (
    BiEncoderConfig,
    load_retriever,
    save_retriever,
    train_bi_encoder,
)
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage2.skill_corpora import skill_corpus_hash

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = ROOT / "artifacts" / "stage2" / "m251"
DEFAULT_RUNS = ROOT / "runs" / "m251_learned"


def train_condition(registry_path, dataset_dir, output_dir, config, device):
    verify_fair_blind_freeze(dataset_dir)
    registry = SkillRegistry.load(registry_path)
    retriever, training = train_bi_encoder(
        registry,
        load_jsonl(dataset_dir / "train.jsonl"),
        load_jsonl(dataset_dir / "calibration.jsonl"),
        config=config,
        device=device,
    )
    validation = evaluate_fair_retriever(
        retriever, load_jsonl(dataset_dir / "validation.jsonl")
    )
    development = evaluate_fair_retriever(
        retriever, load_jsonl(dataset_dir / "development.jsonl")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{config.corpus_condition}_seed_{config.seed}"
    save_retriever(retriever, output_dir / f"{stem}.pt", training)
    result = {
        "config": asdict(config),
        "training": training,
        "validation": validation,
        "development": development,
        "checkpoint": f"{stem}.pt",
        "blind_opened": False,
    }
    _write_json(output_dir / f"{stem}_development.json", result)
    return result


def freeze_recipe(registry_path, dataset_dir, output_dir, conditions, seed, config):
    verify_fair_blind_freeze(dataset_dir)
    registry = SkillRegistry.load(registry_path)
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    development = {}
    for condition in conditions:
        path = output_dir / f"{condition}_seed_{seed}_development.json"
        development[condition] = json.loads(path.read_text(encoding="utf-8"))
    primary = development[config.corpus_condition]["development"]
    eligible = (
        primary["top5"] >= 0.95
        and primary["hard_neighbor"]["pairwise_target_over_neighbor_accuracy"] >= 0.80
        and primary["abstention"]["false_known_rate"] <= 0.05
    )
    recipe = {
        "schema_version": 2,
        "architecture": "hashed_char_word_4096_128_96_bi_encoder",
        "conditions": conditions,
        "primary_condition": config.corpus_condition,
        "config": asdict(config),
        "condition_configs": {
            condition: result["config"] for condition, result in development.items()
        },
        "seed": seed,
        "multi_seed_eligible": eligible,
        "calibration_method": "calibration_only_false_known_bound",
        "targeted_ablation_count": 1,
        "targeted_ablation": "explicit_register_operation_token_features",
        "hard_negative_mining_rounds": 0,
        "blind_open_policy": "single_atomic_open_all_predeclared_conditions",
        "blind_public_sha256": manifest["blind_public_sha256"],
        "blind_targets_sha256": manifest["blind_targets_sha256"],
        "query_surface_inventory_hash": manifest["query_surface_inventory_hash"],
        "ood_split_definition_hash": manifest["ood_split_definition_hash"],
        "skill_corpus_hashes": {
            condition: skill_corpus_hash(registry.active_records(), condition)
            for condition in conditions
        },
        "development_result_hashes": {
            condition: content_hash(result) for condition, result in development.items()
        },
        "frozen_at": utc_now(),
    }
    recipe["recipe_hash"] = content_hash(recipe)
    _write_json(output_dir / "recipe_freeze.json", recipe)
    return recipe


def open_blind_once(registry_path, dataset_dir, output_dir, *, device="cpu"):
    verify_fair_blind_freeze(dataset_dir)
    final_path = output_dir / "blind_final.json"
    if final_path.exists():
        raise ValueError("V2 blind has already been opened")
    recipe = _verified_recipe(output_dir)
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in (
        "blind_public_sha256",
        "blind_targets_sha256",
        "query_surface_inventory_hash",
        "ood_split_definition_hash",
    ):
        if recipe[key] != manifest[key]:
            raise ValueError(f"frozen {key} changed")
    registry = SkillRegistry.load(registry_path)
    blind = load_fair_blind(dataset_dir)
    results = {}
    for condition in recipe["conditions"]:
        checkpoint = output_dir / f"{condition}_seed_{recipe['seed']}.pt"
        retriever = load_retriever(
            checkpoint, device=device, allow_archival_research=True
        )
        if retriever.registry_hash != registry.manifest.registry_hash:
            raise ValueError("checkpoint registry hash mismatch")
        results[condition] = evaluate_fair_retriever(retriever, blind)
    final = {
        "recipe_hash": recipe["recipe_hash"],
        "opened_once_at": utc_now(),
        "condition_results": results,
        "primary_condition": recipe["primary_condition"],
        "label_leakage": diagnose_label_leakage(
            load_jsonl(dataset_dir / "train.jsonl"),
            blind,
            registry.active_records(),
        ),
        "deterministic_baselines": evaluate_fair_deterministic_baselines(
            registry.active_records(), blind
        ),
    }
    _write_json(final_path, final)
    return final


def verify_evidence(registry_path, dataset_dir, output_dir, *, device="cpu"):
    verify_fair_blind_freeze(dataset_dir)
    recipe = _verified_recipe(output_dir)
    final = json.loads((output_dir / "blind_final.json").read_text(encoding="utf-8"))
    if final["recipe_hash"] != recipe["recipe_hash"]:
        raise ValueError("blind result recipe hash mismatch")
    registry = SkillRegistry.load(registry_path)
    for condition in recipe["conditions"]:
        retriever = load_retriever(
            output_dir / f"{condition}_seed_{recipe['seed']}.pt",
            device=device,
            allow_archival_research=True,
        )
        if retriever.registry_hash != registry.manifest.registry_hash:
            raise ValueError("checkpoint registry hash mismatch")
    result = {
        "status": "VALID",
        "recipe_hash": recipe["recipe_hash"],
        "conditions": recipe["conditions"],
        "verified_at": utc_now(),
    }
    _write_json(output_dir / "evidence_verification.json", result)
    return result


def _verified_recipe(output_dir):
    recipe = json.loads((output_dir / "recipe_freeze.json").read_text(encoding="utf-8"))
    expected = recipe.pop("recipe_hash")
    if content_hash(recipe) != expected:
        raise ValueError("recipe freeze hash mismatch")
    return {**recipe, "recipe_hash": expected}


def _config(args, condition):
    return BiEncoderConfig(
        feature_count=4096,
        hidden_size=128,
        embedding_size=96,
        learning_rate=args.learning_rate,
        temperature=args.temperature,
        batch_size=args.batch_size,
        steps=args.steps,
        seed=args.seed,
        false_known_bound=args.false_known_bound,
        corpus_condition=condition,
        hard_negative_weight=args.hard_negative_weight,
        hard_negative_margin=args.hard_negative_margin,
        explicit_semantic_features=args.explicit_semantic_features,
    )


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("train", "freeze", "blind", "verify"))
    parser.add_argument(
        "--registry", type=Path, default=DEFAULT_ARTIFACTS / "skill_registry_v2.json"
    )
    parser.add_argument(
        "--dataset-dir", type=Path, default=DEFAULT_ARTIFACTS / "queries_v2"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument(
        "--condition", choices=("rich", "sanitized", "minimal"), default="sanitized"
    )
    parser.add_argument("--conditions", default="rich,sanitized,minimal")
    parser.add_argument("--seed", type=int, default=25_101)
    parser.add_argument("--device")
    parser.add_argument("--steps", type=int, default=1500)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=2e-3)
    parser.add_argument("--temperature", type=float, default=0.08)
    parser.add_argument("--false-known-bound", type=float, default=0.05)
    parser.add_argument("--hard-negative-weight", type=float, default=1.0)
    parser.add_argument("--hard-negative-margin", type=float, default=0.15)
    parser.add_argument("--explicit-semantic-features", action="store_true")
    args = parser.parse_args()
    config = _config(args, args.condition)
    if args.command == "train":
        result = train_condition(
            args.registry, args.dataset_dir, args.output_dir, config, args.device
        )
    elif args.command == "freeze":
        result = freeze_recipe(
            args.registry,
            args.dataset_dir,
            args.output_dir,
            args.conditions.split(","),
            args.seed,
            config,
        )
    elif args.command == "blind":
        result = open_blind_once(
            args.registry,
            args.dataset_dir,
            args.output_dir,
            device=args.device or "cpu",
        )
    else:
        result = verify_evidence(
            args.registry,
            args.dataset_dir,
            args.output_dir,
            device=args.device or "cpu",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
