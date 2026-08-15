from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.model.config import get_named_model_config
from ai_brain.model.factory import build_model
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m163_clean_arithmetic"
RUNS_DIR = ROOT / "runs" / "m163_clean_arithmetic"
DOC_PATH = ROOT / "docs" / "m163_clean_arithmetic_capacity_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m163_clean_arithmetic_capacity_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"
M14_DIR = ROOT / "datasets" / "m14_digit_table_curriculum"

TRAIN_BASE_COMBO_COUNT = 3000
EVAL_COUNT = 500
SEED = 316300
RUN_SEED = 316301
MAX_NEW_TOKENS = 16


@dataclass(frozen=True)
class AdditionCase:
    a: int
    b: int

    @property
    def result(self) -> int:
        return self.a + self.b

    @property
    def a_text(self) -> str:
        return f"{self.a:02d}"

    @property
    def b_text(self) -> str:
        return f"{self.b:02d}"

    @property
    def result_text(self) -> str:
        return str(self.result)

    @property
    def prompt(self) -> str:
        return f"ADD {self.a_text} + {self.b_text}"

    @property
    def output_length(self) -> str:
        return f"{len(self.result_text)}_digit"

    @property
    def units_carry(self) -> int:
        return int((self.a % 10) + (self.b % 10) >= 10)

    @property
    def final_carry(self) -> int:
        return int((self.a // 10) + (self.b // 10) + self.units_carry >= 10)

    @property
    def carry_bucket(self) -> str:
        if self.final_carry:
            return "final_carry"
        if self.units_carry:
            return "units_carry"
        return "no_carry"

    @property
    def composition_key(self) -> str:
        return f"{self.a_text}+{self.b_text}"

    @property
    def local_digit_keys(self) -> tuple[str, str]:
        return (
            f"U:{self.a % 10}:{self.b % 10}:0",
            f"T:{self.a // 10}:{self.b // 10}:{self.units_carry}",
        )


@dataclass(frozen=True)
class RunSpec:
    name: str
    model_config: str
    train_path: Path
    steps: int
    batch_size: int = 8
    init_checkpoint: Path | None = None
    group: str = "capacity"
    seed: int = RUN_SEED


PRIMARY_SPLITS = (
    "eval_train_exact",
    "eval_seen_combo_2digit",
    "eval_seen_combo_3digit",
    "eval_unseen_combo_2digit",
    "eval_unseen_combo_3digit",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-tiny")
    subparsers.add_parser("run-digit-transfer")
    subparsers.add_parser("run-capacity")
    subparsers.add_parser("run-multiseed")
    subparsers.add_parser("analyze")
    subparsers.add_parser("build-report")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-tiny":
        run_specs([_random_tiny_spec()])
        analyze_all()
        build_report()
    elif args.command == "run-digit-transfer":
        run_digit_transfer()
        analyze_all()
        build_report()
    elif args.command == "run-capacity":
        run_specs(_capacity_specs())
        analyze_all()
        build_report()
    elif args.command == "run-multiseed":
        run_specs(_multi_seed_specs())
        analyze_all()
        build_report()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report()
    elif args.command == "run-all":
        prepare_datasets()
        run_specs([_random_tiny_spec()])
        run_digit_transfer()
        run_specs(_capacity_specs())
        analyze_all()
        build_report()
    else:
        raise AssertionError(args.command)
    return 0


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    cases = _all_cases()
    train_cases = _select_train_cases(cases)
    train_keys = {case.composition_key for case in train_cases}

    train_records = [
        _record_for_case(case, split="train", index=index)
        for index, case in enumerate(train_cases)
    ]
    seen_2 = _take_cases(
        [case for case in train_cases if case.output_length == "2_digit"],
        count=EVAL_COUNT,
        seed=SEED + 1,
    )
    seen_3 = _take_cases(
        [case for case in train_cases if case.output_length == "3_digit"],
        count=EVAL_COUNT,
        seed=SEED + 2,
    )
    unseen_2 = _take_cases(
        [
            case
            for case in cases
            if case.composition_key not in train_keys
            and case.output_length == "2_digit"
        ],
        count=EVAL_COUNT,
        seed=SEED + 3,
    )
    unseen_3 = _take_cases(
        [
            case
            for case in cases
            if case.composition_key not in train_keys
            and case.output_length == "3_digit"
        ],
        count=EVAL_COUNT,
        seed=SEED + 4,
    )
    wrapper = _take_cases(train_cases, count=EVAL_COUNT, seed=SEED + 5)

    splits = {
        "train": train_records,
        "eval_train_exact": [
            _record_for_case(case, split="eval_train_exact", index=index)
            for index, case in enumerate(train_cases)
        ],
        "eval_seen_combo_2digit": [
            _record_for_case(case, split="eval_seen_combo_2digit", index=index)
            for index, case in enumerate(seen_2)
        ],
        "eval_seen_combo_3digit": [
            _record_for_case(case, split="eval_seen_combo_3digit", index=index)
            for index, case in enumerate(seen_3)
        ],
        "eval_unseen_combo_2digit": [
            _record_for_case(case, split="eval_unseen_combo_2digit", index=index)
            for index, case in enumerate(unseen_2)
        ],
        "eval_unseen_combo_3digit": [
            _record_for_case(case, split="eval_unseen_combo_3digit", index=index)
            for index, case in enumerate(unseen_3)
        ],
        "eval_wrapper_holdout": [
            _record_for_case(
                case,
                split="eval_wrapper_holdout",
                index=index,
                prompt=f"Compute ADD {case.a_text} + {case.b_text}",
            )
            for index, case in enumerate(wrapper)
        ],
    }
    split_infos = {
        split_name: _write_jsonl(DATASET_DIR / f"{split_name}.jsonl", records)
        for split_name, records in splits.items()
    }
    _write_replay_dataset()

    train_prompts = {record["prompt"] for record in train_records}
    train_combos = {record["metadata"]["composition_key"] for record in train_records}
    manifest = {
        "kind": "m163_clean_arithmetic",
        "seed": SEED,
        "answer_format": "FINAL <number>",
        "numeric_tokenization": "digit_safe",
        "splits": split_infos,
        "quality": {
            name: {
                "prompt_overlap_with_train": len(
                    train_prompts.intersection(record["prompt"] for record in records)
                ),
                "composition_overlap_with_train": len(
                    train_combos.intersection(
                        record["metadata"]["composition_key"] for record in records
                    )
                ),
                "digit_pair_coverage": _digit_pair_coverage(
                    _cases_from_records(records)
                ),
                "carry_distribution": _distribution(
                    record["metadata"]["carry_bucket"] for record in records
                ),
                "output_length_distribution": _distribution(
                    record["metadata"]["output_length"] for record in records
                ),
            }
            for name, records in splits.items()
        },
        "train_digit_pair_coverage": _digit_pair_coverage(train_cases),
        "environment": _environment_snapshot(),
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_digit_transfer() -> None:
    pretrain_checkpoint = _ensure_digit_pretrain()
    replay_path = DATASET_DIR / "train_addition_with_digit_replay.jsonl"
    run_specs(
        [
            RunSpec(
                name="digit_pretrained_tiny_10k",
                model_config="tiny",
                train_path=DATASET_DIR / "train.jsonl",
                steps=10000,
                init_checkpoint=pretrain_checkpoint,
                group="digit_transfer",
            ),
            RunSpec(
                name="digit_pretrained_replay_tiny_10k",
                model_config="tiny",
                train_path=replay_path,
                steps=10000,
                init_checkpoint=pretrain_checkpoint,
                group="digit_transfer",
            ),
        ]
    )


def run_specs(specs: list[RunSpec]) -> None:
    for spec in specs:
        _run_training_and_eval(spec)


def analyze_all() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    for summary_path in sorted((RUNS_DIR / "evals").glob("*/*/summary.json")):
        run_name = summary_path.parents[1].name
        split_name = summary_path.parent.name
        predictions_path = summary_path.parent / "predictions.jsonl"
        eval_path = DATASET_DIR / f"{split_name}.jsonl"
        if not eval_path.exists():
            continue
        results.setdefault(run_name, {})[split_name] = analyze_predictions(
            predictions_path=predictions_path,
            eval_path=eval_path,
        )

    run_metadata = {}
    for run_dir in RUNS_DIR.glob("*_10k"):
        config_path = run_dir / "train_config.json"
        metrics_path = run_dir / "metrics.jsonl"
        if not config_path.exists():
            continue
        train_config = json.loads(config_path.read_text(encoding="utf-8"))
        metrics = _read_jsonl(metrics_path) if metrics_path.exists() else []
        run_metadata[run_dir.name] = {
            "train_config": train_config.get("train_config", {}),
            "model_config": train_config.get("model_config", {}),
            "model": train_config.get("model"),
            "device": train_config.get("device"),
            "device_name": train_config.get("device_name"),
            "initialized_from_checkpoint": train_config.get(
                "initialized_from_checkpoint"
            ),
            "last_metrics": metrics[-1] if metrics else {},
            "wall_time_seconds": _read_wall_time(run_dir),
            "param_count": _param_count_for_config(
                str(train_config.get("train_config", {}).get("model_config_name"))
            ),
        }

    analysis = {
        "results": results,
        "runs": run_metadata,
        "manifest": _read_json(DATASET_DIR / "manifest.json"),
        "environment": _environment_snapshot(),
    }
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def analyze_predictions(*, predictions_path: Path, eval_path: Path) -> dict[str, Any]:
    predictions = _read_jsonl(predictions_path)
    eval_records = {str(record["id"]): record for record in _read_jsonl(eval_path)}
    joined = [
        {**prediction, "metadata": eval_records[str(prediction["id"])]["metadata"]}
        for prediction in predictions
    ]
    return {
        "overall": _metric_slice(joined),
        "buckets": {
            bucket: _metric_slice(_filter_bucket(joined, bucket))
            for bucket in (
                "no_carry",
                "units_carry",
                "final_carry",
                "2_digit",
                "3_digit",
            )
        },
        "failure_samples": _failure_samples(joined),
    }


def build_report() -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    report = _render_report(analysis)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(report, encoding="utf-8")
    RUN_REPORT_PATH.write_text(report, encoding="utf-8")


def _random_tiny_spec() -> RunSpec:
    return RunSpec(
        name="random_tiny_10k",
        model_config="tiny",
        train_path=DATASET_DIR / "train.jsonl",
        steps=10000,
        group="tiny_fit",
    )


def _capacity_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="arithmetic_3m_10k",
            model_config="arithmetic_3m",
            train_path=DATASET_DIR / "train.jsonl",
            steps=10000,
            group="capacity",
        ),
        RunSpec(
            name="arithmetic_10m_10k",
            model_config="arithmetic_10m",
            train_path=DATASET_DIR / "train.jsonl",
            steps=10000,
            group="capacity",
        ),
    ]


def _multi_seed_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="arithmetic_3m_seed316302_10k",
            model_config="arithmetic_3m",
            train_path=DATASET_DIR / "train.jsonl",
            steps=10000,
            group="multi_seed",
            seed=316302,
        ),
        RunSpec(
            name="arithmetic_3m_seed316303_10k",
            model_config="arithmetic_3m",
            train_path=DATASET_DIR / "train.jsonl",
            steps=10000,
            group="multi_seed",
            seed=316303,
        ),
    ]


def _run_training_and_eval(spec: RunSpec) -> None:
    run_dir = RUNS_DIR / spec.name
    checkpoint = run_dir / "checkpoints" / f"step_{spec.steps:06d}.pt"
    if not checkpoint.exists():
        start = time.perf_counter()
        result = train_lm(
            TrainConfig(
                train_path=spec.train_path,
                eval_path=DATASET_DIR / "eval_seen_combo_2digit.jsonl",
                tokenizer_path=TOKENIZER_PATH,
                output_dir=run_dir,
                model_config_name=spec.model_config,
                steps=spec.steps,
                batch_size=spec.batch_size,
                sequence_length=128,
                loss_mode="answer-only",
                learning_rate=3e-4,
                grad_clip_norm=1.0,
                numeric_tokenization="digit_safe",
                seed=spec.seed,
                eval_every=max(spec.steps // 5, 1),
                eval_batches=20,
                save_every=max(spec.steps // 2, 1),
                cache_dir=ROOT / "cache" / "tokenized",
                init_checkpoint_path=spec.init_checkpoint,
            )
        )
        checkpoint = Path(result["checkpoint_paths"][-1])
        (run_dir / "wall_time.json").write_text(
            json.dumps({"seconds": time.perf_counter() - start}, indent=2),
            encoding="utf-8",
        )
    for split_name in PRIMARY_SPLITS:
        output_dir = RUNS_DIR / "evals" / spec.name / split_name
        if (output_dir / "summary.json").exists():
            continue
        eval_lm(
            checkpoint_path=checkpoint,
            eval_path=DATASET_DIR / f"{split_name}.jsonl",
            tokenizer_path=TOKENIZER_PATH,
            output_dir=output_dir,
            max_new_tokens=MAX_NEW_TOKENS,
            seed=spec.seed,
            numeric_tokenization="digit_safe",
        )


def _ensure_digit_pretrain() -> Path:
    if not (M14_DIR / "train_digit_table.jsonl").exists():
        raise FileNotFoundError(
            "Missing M-14 digit table dataset. Run generate-digit-table-curriculum first."
        )
    run_dir = RUNS_DIR / "digit_table_pretrain_tiny_22k"
    checkpoint = run_dir / "checkpoints" / "step_022000.pt"
    if checkpoint.exists():
        return checkpoint
    start = time.perf_counter()
    result = train_lm(
        TrainConfig(
            train_path=M14_DIR / "train_digit_table.jsonl",
            eval_path=M14_DIR / "eval_digit_table_seen.jsonl",
            tokenizer_path=TOKENIZER_PATH,
            output_dir=run_dir,
            model_config_name="tiny",
            steps=22000,
            batch_size=8,
            sequence_length=128,
            loss_mode="answer-only",
            learning_rate=3e-4,
            grad_clip_norm=1.0,
            numeric_tokenization="digit_safe",
            seed=RUN_SEED,
            eval_every=2000,
            eval_batches=20,
            save_every=22000,
            cache_dir=ROOT / "cache" / "tokenized",
        )
    )
    (run_dir / "wall_time.json").write_text(
        json.dumps({"seconds": time.perf_counter() - start}, indent=2),
        encoding="utf-8",
    )
    return Path(result["checkpoint_paths"][-1])


def _write_replay_dataset() -> None:
    addition = _read_jsonl(DATASET_DIR / "train.jsonl")
    if not addition:
        return
    digit_table = _read_jsonl(M14_DIR / "train_digit_table.jsonl")
    rng = random.Random(SEED + 99)
    replay = []
    addition_count = 4800
    digit_count = 1200
    for index in range(addition_count):
        record = dict(addition[index % len(addition)])
        record["id"] = f"replay:add:{index:05d}"
        replay.append(record)
    sampled_digit = [dict(record) for record in rng.sample(digit_table, digit_count)]
    for index, record in enumerate(sampled_digit):
        record["id"] = f"replay:digit:{index:05d}"
        metadata = dict(record.get("metadata", {}))
        metadata["replay_source"] = "digit_table"
        record["metadata"] = metadata
        replay.append(record)
    rng.shuffle(replay)
    _write_jsonl(DATASET_DIR / "train_addition_with_digit_replay.jsonl", replay)


def _all_cases() -> list[AdditionCase]:
    return [
        AdditionCase(a=a, b=b)
        for a in range(100)
        for b in range(100)
        if 10 <= a + b <= 198
    ]


def _select_train_cases(cases: list[AdditionCase]) -> list[AdditionCase]:
    rng = random.Random(SEED)
    remaining = list(cases)
    rng.shuffle(remaining)
    selected: list[AdditionCase] = []
    selected_keys: set[str] = set()
    uncovered = _local_digit_keys_for_cases(cases)
    while uncovered:
        best = max(
            (case for case in remaining if case.composition_key not in selected_keys),
            key=lambda case: len(uncovered.intersection(case.local_digit_keys)),
        )
        gain = uncovered.intersection(best.local_digit_keys)
        if not gain:
            raise RuntimeError("Could not cover all reachable local digit keys")
        selected.append(best)
        selected_keys.add(best.composition_key)
        uncovered.difference_update(gain)

    quotas = {"no_carry": 750, "units_carry": 750, "final_carry": 1500}
    counts = Counter(case.carry_bucket for case in selected)
    for bucket, quota in quotas.items():
        candidates = [
            case
            for case in remaining
            if case.carry_bucket == bucket and case.composition_key not in selected_keys
        ]
        rng.shuffle(candidates)
        for case in candidates:
            if counts[bucket] >= quota:
                break
            selected.append(case)
            selected_keys.add(case.composition_key)
            counts[bucket] += 1
    if len(selected) != TRAIN_BASE_COMBO_COUNT:
        raise RuntimeError(
            f"Expected {TRAIN_BASE_COMBO_COUNT} train cases, got {len(selected)}"
        )
    rng.shuffle(selected)
    return selected


def _take_cases(
    cases: list[AdditionCase], *, count: int, seed: int
) -> list[AdditionCase]:
    if len(cases) < count:
        raise RuntimeError(f"Need {count} cases, only have {len(cases)}")
    shuffled = list(cases)
    random.Random(seed).shuffle(shuffled)
    return shuffled[:count]


def _record_for_case(
    case: AdditionCase,
    *,
    split: str,
    index: int,
    prompt: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{split}:{index:05d}",
        "task_type": "arithmetic.add_clean",
        "prompt": prompt or case.prompt,
        "answer": f"FINAL {case.result_text}",
        "metadata": {
            "a": case.a,
            "b": case.b,
            "a_text": case.a_text,
            "b_text": case.b_text,
            "result": case.result,
            "result_text": case.result_text,
            "output_length": case.output_length,
            "units_carry": case.units_carry,
            "final_carry": case.final_carry,
            "carry_bucket": case.carry_bucket,
            "composition_key": case.composition_key,
            "local_digit_keys": list(case.local_digit_keys),
            "split": split,
        },
    }


def _metric_slice(items: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(items)
    if count == 0:
        return _empty_metrics()
    final_matches = 0
    full_matches = 0
    empty = 0
    false_answers = 0
    token_counts = []
    digit_acc = defaultdict(list)
    for item in items:
        expected = normalize_final_answer(extract_final_answer(str(item["expected"])))
        predicted = normalize_final_answer(extract_final_answer(str(item["predicted"])))
        final_matches += int(predicted == expected)
        full_matches += int(bool(item.get("normalized_exact_match", False)))
        empty += int(predicted == "")
        false_answers += int(predicted != "" and predicted != expected)
        token_counts.append(int(item.get("tokens_generated", 0)))
        for key, value in _digit_accuracies(expected, predicted).items():
            digit_acc[key].append(value)
    return {
        "count": count,
        "normalized_exact_match": full_matches / count,
        "final_normalized_exact_match": final_matches / count,
        "empty_prediction_rate": empty / count,
        "false_answer_rate": false_answers / count,
        "avg_tokens_generated": sum(token_counts) / count,
        **{
            key: sum(values) / len(values) if values else 0.0
            for key, values in digit_acc.items()
        },
    }


def _digit_accuracies(expected: str, predicted: str) -> dict[str, float]:
    expected_digits = expected if expected.isdigit() else ""
    predicted_digits = predicted if predicted.isdigit() else ""
    positions = {
        "units_accuracy": 1,
        "tens_accuracy": 2,
        "hundreds_accuracy": 3,
    }
    result = {}
    correct = 0
    total = max(len(expected_digits), 1)
    for name, offset in positions.items():
        expected_digit = _digit_from_right(expected_digits, offset)
        predicted_digit = _digit_from_right(predicted_digits, offset)
        if not expected_digit:
            continue
        value = float(expected_digit == predicted_digit)
        result[name] = value
        correct += int(value)
    result["per_digit_accuracy"] = correct / total
    result["carry_state_accuracy"] = float(
        (len(expected_digits) == 3) == (len(predicted_digits) == 3)
    )
    return result


def _filter_bucket(items: list[dict[str, Any]], bucket: str) -> list[dict[str, Any]]:
    if bucket in {"2_digit", "3_digit"}:
        return [
            item for item in items if item["metadata"].get("output_length") == bucket
        ]
    return [item for item in items if item["metadata"].get("carry_bucket") == bucket]


def _failure_samples(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples = []
    for item in items:
        expected = normalize_final_answer(extract_final_answer(str(item["expected"])))
        predicted = normalize_final_answer(extract_final_answer(str(item["predicted"])))
        if expected == predicted:
            continue
        samples.append(
            {
                "prompt": item["prompt"],
                "expected": expected,
                "predicted": predicted,
                "carry_bucket": item["metadata"].get("carry_bucket"),
                "wrong_digit": _first_wrong_digit(expected, predicted),
            }
        )
        if len(samples) >= 8:
            break
    return samples


def _render_report(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    results = analysis.get("results", {})
    runs = analysis.get("runs", {})
    decision = _decide(results)
    lines = [
        "# M-16.3 / M-16.4 Clean Arithmetic Capacity Report",
        "",
        "## Checks",
        "",
        "- `uv run ruff format src tests scripts`",
        "- `uv run ruff check src tests scripts`",
        "- `uv run pytest -q`",
        f"- commit: `{analysis.get('environment', {}).get('commit', 'n/a')}`",
        f"- device: `{analysis.get('environment', {}).get('device', 'n/a')}` / `{analysis.get('environment', {}).get('device_name', 'n/a')}`",
        "",
        "## Clean Benchmark Verification",
        "",
        "| split | count | prompt overlap | composition overlap | digit coverage | carry distribution | 2digit/3digit |",
        "| --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for split_name, split_info in sorted(manifest.get("splits", {}).items()):
        quality = manifest.get("quality", {}).get(split_name, {})
        coverage = quality.get("digit_pair_coverage", {})
        lengths = quality.get("output_length_distribution", {})
        lines.append(
            f"| {split_name} | {split_info.get('count', 0)} | "
            f"{quality.get('prompt_overlap_with_train', 0)} | "
            f"{quality.get('composition_overlap_with_train', 0)} | "
            f"{coverage.get('seen_count', 0)}/{coverage.get('required_count', 0)} | "
            f"`{quality.get('carry_distribution', {})}` | "
            f"`{lengths.get('2_digit', 0)}/{lengths.get('3_digit', 0)}` |"
        )
    lines.extend(["", "## Tiny Fit Audit", ""])
    lines.extend(_run_table(results, runs, ["random_tiny_10k"]))
    lines.extend(["", "## Digit-Table Transfer", ""])
    lines.extend(
        _run_table(
            results,
            runs,
            [
                "random_tiny_10k",
                "digit_pretrained_tiny_10k",
                "digit_pretrained_replay_tiny_10k",
            ],
        )
    )
    lines.extend(["", "## Capacity Sweep", ""])
    lines.extend(
        _run_table(
            results,
            runs,
            ["random_tiny_10k", "arithmetic_3m_10k", "arithmetic_10m_10k"],
        )
    )
    lines.extend(["", "## Multi-Seed Results", ""])
    lines.extend(_multi_seed_lines(results))
    lines.extend(["", "## Failure Samples", ""])
    lines.extend(_failure_sample_lines(results))
    lines.extend(["", "## Decision", "", decision["text"], "", "## Next Milestone", ""])
    lines.append(decision["next"])
    return "\n".join(lines).rstrip() + "\n"


def _run_table(
    results: dict[str, Any],
    runs: dict[str, Any],
    run_names: list[str],
) -> list[str]:
    lines = [
        "| variant | params | steps | batch | train loss | eval loss | train NEM | seen2 | seen3 | unseen2 | unseen3 | units | tens | hundreds |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run_name in run_names:
        result = results.get(run_name, {})
        metadata = runs.get(run_name, {})
        config = metadata.get("train_config", {})
        last = metadata.get("last_metrics", {})
        train = _overall(result, "eval_train_exact")
        seen2 = _overall(result, "eval_seen_combo_2digit")
        seen3 = _overall(result, "eval_seen_combo_3digit")
        unseen2 = _overall(result, "eval_unseen_combo_2digit")
        unseen3 = _overall(result, "eval_unseen_combo_3digit")
        lines.append(
            f"| {run_name} | {metadata.get('param_count', 'n/a')} | "
            f"{config.get('steps', 'n/a')} | {config.get('batch_size', 'n/a')} | "
            f"{_fmt(last.get('train_loss'))} | {_fmt(last.get('eval_loss'))} | "
            f"{_fmt(train.get('final_normalized_exact_match'))} | "
            f"{_fmt(seen2.get('final_normalized_exact_match'))} | "
            f"{_fmt(seen3.get('final_normalized_exact_match'))} | "
            f"{_fmt(unseen2.get('final_normalized_exact_match'))} | "
            f"{_fmt(unseen3.get('final_normalized_exact_match'))} | "
            f"{_fmt(_avg_metric([seen2, seen3, unseen2, unseen3], 'units_accuracy'))} | "
            f"{_fmt(_avg_metric([seen2, seen3, unseen2, unseen3], 'tens_accuracy'))} | "
            f"{_fmt(_avg_metric([seen3, unseen3], 'hundreds_accuracy'))} |"
        )
    return lines


def _multi_seed_lines(results: dict[str, Any]) -> list[str]:
    run_names = [
        name
        for name in (
            "arithmetic_3m_10k",
            "arithmetic_3m_seed316302_10k",
            "arithmetic_3m_seed316303_10k",
        )
        if name in results
    ]
    if len(run_names) < 3:
        return [
            (
                "Triggered for `arithmetic_3m`, but only "
                f"{len(run_names)}/3 seeds are available so far."
            )
        ]
    metrics = {
        "train NEM": [
            _nem(results, run_name, "eval_train_exact") for run_name in run_names
        ],
        "seen2": [
            _nem(results, run_name, "eval_seen_combo_2digit") for run_name in run_names
        ],
        "seen3": [
            _nem(results, run_name, "eval_seen_combo_3digit") for run_name in run_names
        ],
        "unseen2": [
            _nem(results, run_name, "eval_unseen_combo_2digit")
            for run_name in run_names
        ],
        "unseen3": [
            _nem(results, run_name, "eval_unseen_combo_3digit")
            for run_name in run_names
        ],
        "units": [
            _avg_metric(
                [
                    _overall(results[run_name], "eval_seen_combo_2digit"),
                    _overall(results[run_name], "eval_seen_combo_3digit"),
                    _overall(results[run_name], "eval_unseen_combo_2digit"),
                    _overall(results[run_name], "eval_unseen_combo_3digit"),
                ],
                "units_accuracy",
            )
            or 0.0
            for run_name in run_names
        ],
    }
    lines = [
        "`arithmetic_3m` triggered multi-seed validation because it improved unseen-combo NEM over S0.",
        "",
        "| metric | mean | std | min | max |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for metric_name, values in metrics.items():
        lines.append(
            f"| {metric_name} | {_fmt(mean(values))} | {_fmt(pstdev(values))} | "
            f"{_fmt(min(values))} | {_fmt(max(values))} |"
        )
    return lines


def _decide(results: dict[str, Any]) -> dict[str, str]:
    random_train = _nem(results, "random_tiny_10k", "eval_train_exact")
    s1_train = _nem(results, "arithmetic_3m_10k", "eval_train_exact")
    s2_train = _nem(results, "arithmetic_10m_10k", "eval_train_exact")
    s2_seen = min(
        _nem(results, "arithmetic_10m_10k", "eval_seen_combo_2digit"),
        _nem(results, "arithmetic_10m_10k", "eval_seen_combo_3digit"),
    )
    s2_unseen = min(
        _nem(results, "arithmetic_10m_10k", "eval_unseen_combo_2digit"),
        _nem(results, "arithmetic_10m_10k", "eval_unseen_combo_3digit"),
    )
    if max(random_train, s1_train, s2_train) < 0.95:
        return {
            "text": "Outcome E: even the tested models did not fit clean train reliably enough. Inspect data/objective/training before adding new architecture.",
            "next": "Next milestone should be training/data debugging on the clean benchmark, with particular focus on units digit supervision and generation format.",
        }
    if max(random_train, s1_train, s2_train) < 0.99:
        return {
            "text": (
                "Outcome E: the clean benchmark removed the M-16.2 wrapper/noise "
                "failure and shows high transfer, but no tested model reached the "
                "strong train-fit criterion of 0.99 reliably. This is not a clean "
                "systematic-rule failure yet."
            ),
            "next": (
                "Inspect clean eval/data/objective details and generation failures "
                "before M-17. A short 20k clean-fit follow-up for the smallest strong "
                "model is more justified than RFFT right now."
            ),
        }
    if random_train < 0.95 and max(s1_train, s2_train) >= 0.95:
        return {
            "text": "Outcome A: capacity threshold is real; bigger models fit clean train much better than S0.",
            "next": "Use the smallest model that fits train as the arithmetic baseline before adding RFFT.",
        }
    if s2_train >= 0.99 and s2_seen >= 0.95 and s2_unseen >= 0.7:
        return {
            "text": "Outcome B: clean arithmetic is mostly below the previous capacity/data threshold.",
            "next": "Do not implement RFFT yet; promote the smallest successful capacity model.",
        }
    if s2_train >= 0.99 and s2_seen >= 0.95 and s2_unseen < 0.7:
        return {
            "text": "Outcome C: clean systematic rule-generalization failure.",
            "next": "Prepare M-17 Rule-Following / RFFT with explicit ADD_DIGIT and ADD_NUMBER supervision.",
        }
    return {
        "text": "Outcome E: fit reliability remains the limiting diagnostic; no clean RFFT trigger yet.",
        "next": "Continue clean fit debugging or extend the smallest improving capacity run to 20k before architecture work.",
    }


def _failure_sample_lines(results: dict[str, Any]) -> list[str]:
    lines = []
    for run_name, run_result in sorted(results.items()):
        split = run_result.get("eval_unseen_combo_2digit") or run_result.get(
            "eval_train_exact", {}
        )
        samples = split.get("failure_samples", [])
        if not samples:
            continue
        lines.extend([f"### {run_name}", ""])
        for sample in samples[:5]:
            lines.append(
                f"- `{sample['prompt']}` expected `{sample['expected']}`, "
                f"predicted `{sample['predicted']}`, carry `{sample['carry_bucket']}`, "
                f"wrong `{sample['wrong_digit']}`"
            )
        lines.append("")
    return lines


def _overall(result: dict[str, Any], split_name: str) -> dict[str, Any]:
    return result.get(split_name, {}).get("overall", {})


def _nem(results: dict[str, Any], run_name: str, split_name: str) -> float:
    return float(
        results.get(run_name, {})
        .get(split_name, {})
        .get("overall", {})
        .get("final_normalized_exact_match", 0.0)
    )


def _avg_metric(items: list[dict[str, Any]], key: str) -> float | None:
    values = [float(item[key]) for item in items if key in item]
    if not values:
        return None
    return sum(values) / len(values)


def _empty_metrics() -> dict[str, Any]:
    return {
        "count": 0,
        "normalized_exact_match": 0.0,
        "final_normalized_exact_match": 0.0,
        "empty_prediction_rate": 0.0,
        "false_answer_rate": 0.0,
        "avg_tokens_generated": 0.0,
        "per_digit_accuracy": 0.0,
        "units_accuracy": 0.0,
        "tens_accuracy": 0.0,
        "hundreds_accuracy": 0.0,
        "carry_state_accuracy": 0.0,
    }


def _first_wrong_digit(expected: str, predicted: str) -> str:
    for label, offset in (("units", 1), ("tens", 2), ("hundreds", 3)):
        expected_digit = _digit_from_right(expected, offset)
        predicted_digit = _digit_from_right(predicted, offset)
        if expected_digit and expected_digit != predicted_digit:
            return label
    if len(expected) != len(predicted):
        return "carry/length"
    return "unknown"


def _digit_from_right(value: str, offset: int) -> str:
    if len(value) < offset:
        return ""
    return value[-offset]


def _cases_from_records(records: Iterable[dict[str, Any]]) -> list[AdditionCase]:
    return [
        AdditionCase(a=int(record["metadata"]["a"]), b=int(record["metadata"]["b"]))
        for record in records
        if "a" in record.get("metadata", {})
    ]


def _local_digit_keys_for_cases(cases: Iterable[AdditionCase]) -> set[str]:
    return {key for case in cases for key in case.local_digit_keys}


def _digit_pair_coverage(cases: Iterable[AdditionCase]) -> dict[str, Any]:
    seen = _local_digit_keys_for_cases(cases)
    required = _local_digit_keys_for_cases(_all_cases())
    return {
        "required_count": len(required),
        "seen_count": len(seen),
        "complete": seen == required,
        "missing": sorted(required - seen)[:20],
    }


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    return dict(Counter(str(value) for value in values))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")
    return {
        "path": str(path),
        "count": len(records),
        "task_type_counts": dict(Counter(record["task_type"] for record in records)),
    }


def _param_count_for_config(name: str) -> int:
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    config = get_named_model_config(name)
    config = type(config)(**{**config.__dict__, "vocab_size": tokenizer.vocab_size})
    model = build_model(config)
    return sum(parameter.numel() for parameter in model.parameters())


def _read_wall_time(run_dir: Path) -> float | None:
    data = _read_json(run_dir / "wall_time.json")
    if not data:
        return None
    return float(data.get("seconds", 0.0))


def _environment_snapshot() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    device = get_device_info()
    return {
        "commit": commit,
        "device": str(device.device),
        "device_name": device.name,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
