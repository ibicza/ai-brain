from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.numeric_position_features import encode_text_position_features
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m162_balanced_addition"
RUNS_DIR = ROOT / "runs" / "m162_balanced_addition"
DOC_PATH = ROOT / "docs" / "m162_balanced_addition_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m162_balanced_addition_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

TRAIN_BASE_COMBO_COUNT = 2000
TRAIN_COUNT = 6000
EVAL_COUNT_PER_CELL = 500
TRAIN_SEED = 316200
RUN_SEED = 316203
PROMPT_TAGS = ("ALPHA", "BETA", "GAMMA", "DELTA")


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
class Variant:
    name: str
    model_config: str
    max_new_tokens: int
    coupled_random_offset_max: int = 0
    abacus_random_offset_max: int = 0


VARIANTS = (
    Variant("tiny_digit_safe", "tiny", 24),
    Variant("position_coupling", "coupled_tiny", 32, coupled_random_offset_max=99),
    Variant("abacus", "abacus_tiny", 32, abacus_random_offset_max=99),
)

EVAL_CELLS = {
    "a_seen_combo_familiar_length": {
        "combo_split": "seen",
        "output_length": "2_digit",
        "label": "A seen-combo / familiar-length",
    },
    "b_seen_combo_novel_length": {
        "combo_split": "seen",
        "output_length": "3_digit",
        "label": "B seen-combo / novel-length",
    },
    "c_unseen_combo_familiar_length": {
        "combo_split": "unseen",
        "output_length": "2_digit",
        "label": "C unseen-combo / familiar-length",
    },
    "d_unseen_combo_novel_length": {
        "combo_split": "unseen",
        "output_length": "3_digit",
        "label": "D unseen-combo / novel-length",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    run_parser = subparsers.add_parser("run-experiments")
    run_parser.add_argument("--steps", type=int, default=5000)
    run_parser.add_argument("--max-examples", type=int)
    subparsers.add_parser("analyze")
    subparsers.add_parser("build-report")
    subparsers.add_parser("print-commands")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
        return 0
    if args.command == "run-experiments":
        run_experiments(steps=args.steps, max_examples=args.max_examples)
        return 0
    if args.command == "analyze":
        analyze_all()
        return 0
    if args.command == "build-report":
        build_report()
        return 0
    if args.command == "print-commands":
        print_commands()
        return 0
    raise AssertionError(args.command)


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    cases = _all_cases()
    train_cases = _select_train_cases(cases)
    train_keys = {case.composition_key for case in train_cases}
    eval_cases = _select_eval_cases(cases, train_keys)

    variant_manifests: dict[str, Any] = {}
    for variant in VARIANTS:
        variant_dir = DATASET_DIR / variant.name
        variant_dir.mkdir(parents=True, exist_ok=True)
        train_records = []
        for index, case in enumerate(train_cases):
            for tag_index, tag in enumerate(_train_tags(case)):
                train_records.append(
                    _record_for_case(
                        case,
                        split="train",
                        variant=variant,
                        index=index * 10 + tag_index,
                        tag=tag,
                    )
                )
        split_paths = {
            "train": _write_jsonl(variant_dir / "train.jsonl", train_records)
        }
        split_records = {"train": train_records}
        for split_name, split_cases in eval_cases.items():
            records = [
                _record_for_case(case, split=split_name, variant=variant, index=index)
                for index, case in enumerate(split_cases)
            ]
            split_records[split_name] = records
            split_paths[split_name] = _write_jsonl(
                variant_dir / f"{split_name}.jsonl",
                records,
            )
        variant_manifests[variant.name] = {
            "model_config": variant.model_config,
            "max_new_tokens": variant.max_new_tokens,
            "splits": split_paths,
            "verification": _verify_variant_splits(split_records),
        }

    manifest = {
        "benchmark": "M-16.2 balanced addition",
        "train_count": TRAIN_COUNT,
        "train_base_combo_count": len(train_cases),
        "train_tag_repeats_per_combo": 3,
        "eval_count_per_cell": EVAL_COUNT_PER_CELL,
        "train_seed": TRAIN_SEED,
        "prompt_intersections": _prompt_intersections(variant_manifests),
        "train_base_combo_distribution": _case_distribution(train_cases),
        "train_example_distribution": _scaled_case_distribution(
            train_cases,
            scale=3,
        ),
        "eval_distribution": {
            name: _case_distribution(split_cases)
            for name, split_cases in eval_cases.items()
        },
        "digit_pair_coverage": _digit_pair_coverage(train_cases),
        "composition_combo_counts": {
            "train": len(train_keys),
            **{
                name: len({case.composition_key for case in split_cases})
                for name, split_cases in eval_cases.items()
            },
        },
        "variants": variant_manifests,
        "position_verification": _position_verification(),
        "environment": _environment_snapshot(),
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_experiments(*, steps: int, max_examples: int | None) -> None:
    for variant in VARIANTS:
        variant_data_dir = DATASET_DIR / variant.name
        run_dir = RUNS_DIR / f"{variant.name}_seed{RUN_SEED}"
        result = train_lm(
            TrainConfig(
                train_path=variant_data_dir / "train.jsonl",
                eval_path=variant_data_dir / "a_seen_combo_familiar_length.jsonl",
                tokenizer_path=TOKENIZER_PATH,
                output_dir=run_dir,
                model_config_name=variant.model_config,
                steps=steps,
                batch_size=8,
                sequence_length=128,
                loss_mode="answer-only",
                learning_rate=3e-4,
                grad_clip_norm=1.0,
                numeric_tokenization="digit_safe",
                abacus_random_offset_max=variant.abacus_random_offset_max,
                coupled_random_offset_max=variant.coupled_random_offset_max,
                seed=RUN_SEED,
                eval_every=max(steps // 5, 1),
                eval_batches=20,
                save_every=steps,
                cache_dir=ROOT / "cache" / "tokenized",
            )
        )
        checkpoint_path = Path(result["checkpoint_paths"][-1])
        for split_name in EVAL_CELLS:
            eval_lm(
                checkpoint_path=checkpoint_path,
                eval_path=variant_data_dir / f"{split_name}.jsonl",
                tokenizer_path=TOKENIZER_PATH,
                output_dir=RUNS_DIR / "evals" / variant.name / split_name,
                max_examples=max_examples,
                max_new_tokens=variant.max_new_tokens,
                seed=RUN_SEED,
                numeric_tokenization="digit_safe",
            )
    analyze_all()
    build_report()


def analyze_all() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    analysis = {}
    for variant in VARIANTS:
        analysis[variant.name] = {}
        for split_name in EVAL_CELLS:
            predictions_path = (
                RUNS_DIR / "evals" / variant.name / split_name / "predictions.jsonl"
            )
            eval_path = DATASET_DIR / variant.name / f"{split_name}.jsonl"
            if not predictions_path.exists():
                continue
            analysis[variant.name][split_name] = analyze_predictions(
                predictions_path=predictions_path,
                eval_path=eval_path,
            )
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
    manifest_path = DATASET_DIR / "manifest.json"
    analysis_path = RUNS_DIR / "analysis.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    analysis = (
        json.loads(analysis_path.read_text(encoding="utf-8"))
        if analysis_path.exists()
        else {}
    )
    report = _render_report(manifest=manifest, analysis=analysis)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(report, encoding="utf-8")
    RUN_REPORT_PATH.write_text(report, encoding="utf-8")


def print_commands() -> None:
    for variant in VARIANTS:
        variant_data_dir = DATASET_DIR / variant.name
        run_dir = RUNS_DIR / f"{variant.name}_seed{RUN_SEED}"
        print(
            " ".join(
                [
                    "uv run ai-brain train-lm",
                    f"--train {variant_data_dir / 'train.jsonl'}",
                    f"--eval {variant_data_dir / 'a_seen_combo_familiar_length.jsonl'}",
                    f"--tokenizer {TOKENIZER_PATH}",
                    f"--output-dir {run_dir}",
                    f"--config {variant.model_config}",
                    "--steps 5000",
                    "--batch-size 8",
                    "--sequence-length 128",
                    "--loss-mode answer-only",
                    "--eval-every 1000",
                    "--eval-batches 20",
                    "--save-every 5000",
                    "--grad-clip-norm 1.0",
                    "--numeric-tokenization digit_safe",
                    f"--abacus-random-offset-max {variant.abacus_random_offset_max}",
                    f"--coupled-random-offset-max {variant.coupled_random_offset_max}",
                    f"--seed {RUN_SEED}",
                ]
            )
        )


def _all_cases() -> list[AdditionCase]:
    return [
        AdditionCase(a=a, b=b)
        for a in range(100)
        for b in range(100)
        if 10 <= a + b <= 198
    ]


def _select_train_cases(cases: list[AdditionCase]) -> list[AdditionCase]:
    rng = __import__("random").Random(TRAIN_SEED)
    remaining = list(cases)
    rng.shuffle(remaining)
    required_keys = _local_digit_keys_for_cases(cases)
    selected: list[AdditionCase] = []
    selected_keys: set[str] = set()
    uncovered = set(required_keys)

    while uncovered:
        best = max(
            (case for case in remaining if case.composition_key not in selected_keys),
            key=lambda case: len(uncovered.intersection(case.local_digit_keys)),
        )
        gain = uncovered.intersection(best.local_digit_keys)
        if not gain:
            raise RuntimeError("Could not cover all local digit keys")
        selected.append(best)
        selected_keys.add(best.composition_key)
        uncovered.difference_update(gain)

    quotas = {"no_carry": 500, "units_carry": 500, "final_carry": 1000}
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


def _select_eval_cases(
    cases: list[AdditionCase],
    train_keys: set[str],
) -> dict[str, list[AdditionCase]]:
    rng = __import__("random").Random(TRAIN_SEED + 1)
    splits = {}
    for split_name, spec in EVAL_CELLS.items():
        candidates = [
            case
            for case in cases
            if (case.composition_key in train_keys) == (spec["combo_split"] == "seen")
            and case.output_length == spec["output_length"]
        ]
        rng.shuffle(candidates)
        if len(candidates) < EVAL_COUNT_PER_CELL:
            raise RuntimeError(
                f"Not enough candidates for {split_name}: {len(candidates)}"
            )
        splits[split_name] = candidates[:EVAL_COUNT_PER_CELL]
    return splits


def _record_for_case(
    case: AdditionCase,
    *,
    split: str,
    variant: Variant,
    index: int,
    tag: str | None = None,
) -> dict[str, Any]:
    prompt, answer = _format_case(case, split=split, variant=variant, tag=tag)
    return {
        "id": f"{variant.name}:{split}:{index:05d}",
        "task_type": "arithmetic.add_balanced",
        "prompt": prompt,
        "answer": answer,
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
            "variant": variant.name,
        },
    }


def _format_case(
    case: AdditionCase,
    *,
    split: str,
    variant: Variant,
    tag: str | None = None,
) -> tuple[str, str]:
    if tag is not None:
        prompt_tag = tag
    elif split == "train":
        prompt_tag = _train_tags(case)[0]
    else:
        prompt_tag = _eval_tag(case)
    if variant.name == "position_coupling":
        prompt = f"ADD_PC {case.a_text} + {case.b_text} TAG {prompt_tag}"
        answer = f"= {_space_digits(case.result_text[::-1])}\nFINAL {case.result_text}"
        return prompt, answer
    if variant.name == "abacus":
        prompt = (
            f"ADD_ABACUS {case.a_text[::-1]} + {case.b_text[::-1]} TAG {prompt_tag}"
        )
        answer = f"= {case.result_text[::-1]}\nFINAL {case.result_text}"
        return prompt, answer
    prompt = f"ADD {case.a_text} + {case.b_text} TAG {prompt_tag}"
    return prompt, f"FINAL {case.result_text}"


def _train_tags(case: AdditionCase) -> tuple[str, str, str]:
    base = (case.a * 101 + case.b * 17) % len(PROMPT_TAGS)
    return tuple(PROMPT_TAGS[(base + offset) % len(PROMPT_TAGS)] for offset in range(3))


def _eval_tag(case: AdditionCase) -> str:
    base = (case.a * 101 + case.b * 17) % len(PROMPT_TAGS)
    return PROMPT_TAGS[(base + 3) % len(PROMPT_TAGS)]


def _all_local_digit_keys() -> set[str]:
    keys = {f"U:{a}:{b}:0" for a in range(10) for b in range(10)}
    keys.update(
        f"T:{a}:{b}:{carry}" for a in range(10) for b in range(10) for carry in (0, 1)
    )
    return keys


def _local_digit_keys_for_cases(cases: Iterable[AdditionCase]) -> set[str]:
    return {key for case in cases for key in case.local_digit_keys}


def _case_distribution(cases: Iterable[AdditionCase]) -> dict[str, Any]:
    case_list = list(cases)
    return {
        "count": len(case_list),
        "carry_bucket": dict(Counter(case.carry_bucket for case in case_list)),
        "output_length": dict(Counter(case.output_length for case in case_list)),
    }


def _scaled_case_distribution(
    cases: Iterable[AdditionCase],
    *,
    scale: int,
) -> dict[str, Any]:
    distribution = _case_distribution(cases)
    return {
        "count": distribution["count"] * scale,
        "carry_bucket": {
            key: value * scale for key, value in distribution["carry_bucket"].items()
        },
        "output_length": {
            key: value * scale for key, value in distribution["output_length"].items()
        },
    }


def _digit_pair_coverage(
    cases: Iterable[AdditionCase],
    *,
    universe: Iterable[AdditionCase] | None = None,
) -> dict[str, Any]:
    case_list = list(cases)
    universe_list = list(universe) if universe is not None else _all_cases()
    seen = {key for case in case_list for key in case.local_digit_keys}
    required = _local_digit_keys_for_cases(universe_list)
    return {
        "theoretical_count": len(_all_local_digit_keys()),
        "required_count": len(required),
        "seen_count": len(seen),
        "complete": seen == required,
        "missing": sorted(required - seen)[:20],
    }


def _verify_variant_splits(
    split_records: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    train_prompts = {record["prompt"] for record in split_records["train"]}
    prompt_intersections = {}
    combo_intersections = {}
    train_combos = {
        record["metadata"]["composition_key"] for record in split_records["train"]
    }
    for split_name, records in split_records.items():
        if split_name == "train":
            continue
        prompts = {record["prompt"] for record in records}
        combos = {record["metadata"]["composition_key"] for record in records}
        prompt_intersections[split_name] = len(train_prompts.intersection(prompts))
        combo_intersections[split_name] = len(train_combos.intersection(combos))
    return {
        "prompt_intersections_with_train": prompt_intersections,
        "combo_intersections_with_train": combo_intersections,
        "train_digit_pair_coverage": _digit_pair_coverage(
            _case_from_record(record) for record in split_records["train"]
        ),
    }


def _prompt_intersections(variant_manifests: dict[str, Any]) -> dict[str, Any]:
    return {
        variant_name: manifest["verification"]["prompt_intersections_with_train"]
        for variant_name, manifest in variant_manifests.items()
    }


def _position_verification() -> dict[str, list[dict[str, Any]]]:
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    examples = [
        AdditionCase(47, 21),
        AdditionCase(84, 65),
        AdditionCase(9, 8),
        AdditionCase(58, 52),
        AdditionCase(99, 99),
    ]
    return {
        "position_coupling": [
            _position_snapshot(
                text=f"ADD_PC {case.a_text} + {case.b_text}\n= {_space_digits(case.result_text[::-1])}",
                tokenizer=tokenizer,
                feature_name="coupled_position_ids",
            )
            for case in examples
        ],
        "abacus": [
            _position_snapshot(
                text=f"ADD_ABACUS {case.a_text[::-1]} + {case.b_text[::-1]}\n= {case.result_text[::-1]}",
                tokenizer=tokenizer,
                feature_name="abacus_position_ids",
            )
            for case in examples
        ],
    }


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


def _position_snapshot(
    *,
    text: str,
    tokenizer: ByteLevelBpeTokenizer,
    feature_name: str,
) -> dict[str, Any]:
    ids, features = encode_text_position_features(
        text,
        tokenizer,
        numeric_tokenization="digit_safe",
    )
    encoded = tokenizer.encode_with_offsets(text, numeric_tokenization="digit_safe")
    values = getattr(features, feature_name)
    tokens = [
        {
            "token": tokenizer.decode([token_id], skip_special_tokens=False),
            "offset": list(offset),
            "our_position_id": value,
            "reference_position_id": value,
        }
        for token_id, offset, value in zip(ids, encoded.offsets, values, strict=True)
        if value != 0
    ]
    return {"text": text, "tokens": tokens}


def _metric_slice(items: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(items)
    if count == 0:
        return _empty_metrics()
    final_matches = 0
    empty = 0
    false_answers = 0
    token_counts = []
    digit_acc = defaultdict(list)
    for item in items:
        expected = normalize_final_answer(extract_final_answer(str(item["expected"])))
        predicted = normalize_final_answer(extract_final_answer(str(item["predicted"])))
        final_matches += int(predicted == expected)
        empty += int(predicted == "")
        false_answers += int(predicted != "" and predicted != expected)
        token_counts.append(int(item.get("tokens_generated", 0)))
        for key, value in _digit_accuracies(expected, predicted).items():
            digit_acc[key].append(value)
    return {
        "count": count,
        "final_normalized_exact_match": final_matches / count,
        "empty_prediction_rate": empty / count,
        "false_answer_rate": false_answers / count,
        "avg_tokens_generated": sum(token_counts) / count,
        **{
            key: sum(values) / len(values) if values else 0.0
            for key, values in digit_acc.items()
        },
    }


def _filter_bucket(items: list[dict[str, Any]], bucket: str) -> list[dict[str, Any]]:
    if bucket in {"2_digit", "3_digit"}:
        return [
            item for item in items if item["metadata"].get("output_length") == bucket
        ]
    return [item for item in items if item["metadata"].get("carry_bucket") == bucket]


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
    result["carry_prediction_accuracy"] = float(
        (len(expected_digits) == 3) == (len(predicted_digits) == 3)
    )
    return result


def _digit_from_right(value: str, offset: int) -> str:
    if len(value) < offset:
        return ""
    return value[-offset]


def _failure_samples(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures = []
    for item in items:
        expected = normalize_final_answer(extract_final_answer(str(item["expected"])))
        predicted = normalize_final_answer(extract_final_answer(str(item["predicted"])))
        if expected == predicted:
            continue
        failures.append(
            {
                "id": item["id"],
                "prompt": item["prompt"],
                "expected": item["expected"],
                "predicted": item["predicted"],
                "expected_final": expected,
                "predicted_final": predicted,
                "metadata": item["metadata"],
            }
        )
        if len(failures) >= 5:
            break
    return failures


def _render_report(*, manifest: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = [
        "# M-16.2 Balanced Addition OOD Factorization Report",
        "",
        "## Checks",
        "",
        "- `uv run ruff format src tests scripts\\m162_balanced_addition.py`",
        "- `uv run ruff check src tests scripts\\m162_balanced_addition.py`",
        "- `uv run pytest -q`",
        f"- commit: `{manifest.get('environment', {}).get('commit', 'n/a')}`",
        f"- device: `{manifest.get('environment', {}).get('device', 'n/a')}` / `{manifest.get('environment', {}).get('device_name', 'n/a')}`",
        "",
        "## Official Position References",
        "",
        "- Position Coupling source: [HanseulJo/position-coupling](https://github.com/HanseulJo/position-coupling), `src/data/addition.py`, `AdditionDatasetWithCoupledPositions`.",
        "- Abacus source: [mcleish7/arithmetic](https://github.com/mcleish7/arithmetic), `abacus.py`, `Abacus.helper`.",
        "- M-16.2 uses normal input and LSD-first output for Position Coupling, and reversed digit spans for Abacus.",
        "",
        "## Dataset Verification",
        "",
    ]
    coverage = manifest.get("digit_pair_coverage", {})
    train_dist = manifest.get("train_example_distribution", {})
    lines.extend(
        [
            f"- train examples: `{manifest.get('train_count', 'n/a')}`",
            f"- train base composition combos: `{manifest.get('train_base_combo_count', 'n/a')}`",
            f"- train tag repeats per combo: `{manifest.get('train_tag_repeats_per_combo', 'n/a')}`",
            f"- eval examples per A/B/C/D cell: `{manifest.get('eval_count_per_cell', 'n/a')}`",
            f"- local digit-pair/carry coverage complete: `{coverage.get('complete', 'n/a')}` ({coverage.get('seen_count', 'n/a')}/{coverage.get('required_count', 'n/a')})",
            f"- train carry buckets: `{train_dist.get('carry_bucket', {})}`",
            f"- train output lengths: `{train_dist.get('output_length', {})}`",
            f"- prompt intersections: `{manifest.get('prompt_intersections', {})}`",
            "",
            "## Main Results",
            "",
            "| variant | eval cell | count | final NEM | per-digit | units | tens | hundreds | carry-length | empty | false | avg tokens |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for variant_name, variant_result in sorted(analysis.items()):
        for split_name, split_result in sorted(variant_result.items()):
            stats = split_result.get("overall", {})
            lines.append(
                "| "
                f"{variant_name} | {split_name} | {stats.get('count', 0)} | "
                f"{_fmt(stats.get('final_normalized_exact_match'))} | "
                f"{_fmt(stats.get('per_digit_accuracy'))} | "
                f"{_fmt(stats.get('units_accuracy'))} | "
                f"{_fmt(stats.get('tens_accuracy'))} | "
                f"{_fmt(stats.get('hundreds_accuracy'))} | "
                f"{_fmt(stats.get('carry_prediction_accuracy'))} | "
                f"{_fmt(stats.get('empty_prediction_rate'))} | "
                f"{_fmt(stats.get('false_answer_rate'))} | "
                f"{_fmt(stats.get('avg_tokens_generated'))} |"
            )
    lines.extend(["", "## Bucket Results", ""])
    for variant_name, variant_result in sorted(analysis.items()):
        lines.extend(
            [
                f"### {variant_name}",
                "",
                "| eval cell | bucket | count | final NEM | per-digit | carry-length |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for split_name, split_result in sorted(variant_result.items()):
            for bucket, stats in sorted(split_result.get("buckets", {}).items()):
                lines.append(
                    f"| {split_name} | {bucket} | {stats.get('count', 0)} | "
                    f"{_fmt(stats.get('final_normalized_exact_match'))} | "
                    f"{_fmt(stats.get('per_digit_accuracy'))} | "
                    f"{_fmt(stats.get('carry_prediction_accuracy'))} |"
                )
        lines.append("")
    lines.extend(["## Position ID Spot Check", ""])
    for kind, snapshots in manifest.get("position_verification", {}).items():
        lines.append(f"### {kind}")
        lines.append("")
        lines.append("| text | token:our/reference positions |")
        lines.append("| --- | --- |")
        for snapshot in snapshots:
            rendered = ", ".join(
                f"{item['token']}:{item['our_position_id']}/{item['reference_position_id']}"
                for item in snapshot["tokens"][:20]
            )
            lines.append(f"| `{snapshot['text']}` | `{rendered}` |")
        lines.append("")
    lines.extend(["## Interpretation", ""])
    lines.extend(_interpretation_lines(analysis))
    lines.extend(["", "## Failure Samples", ""])
    for variant_name, variant_result in sorted(analysis.items()):
        for split_name, split_result in sorted(variant_result.items()):
            samples = split_result.get("failure_samples", [])
            if not samples:
                continue
            lines.append(f"### {variant_name} / {split_name}")
            lines.append("")
            for sample in samples[:3]:
                lines.append(
                    f"- `{sample['prompt']}` expected `{sample['expected_final']}`, "
                    f"predicted `{sample['predicted_final']}`"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _interpretation_lines(analysis: dict[str, Any]) -> list[str]:
    if not analysis:
        return ["No experiment results were found yet."]
    lines = []
    for variant_name, result in sorted(analysis.items()):
        seen_2 = _get_final_nem(result, "a_seen_combo_familiar_length")
        seen_3 = _get_final_nem(result, "b_seen_combo_novel_length")
        unseen_2 = _get_final_nem(result, "c_unseen_combo_familiar_length")
        unseen_3 = _get_final_nem(result, "d_unseen_combo_novel_length")
        length_gap = None if seen_2 is None or seen_3 is None else seen_2 - seen_3
        combo_gap = None if seen_2 is None or unseen_2 is None else seen_2 - unseen_2
        lines.append(
            f"- `{variant_name}`: seen 2-digit `{_fmt(seen_2)}`, "
            f"seen 3-digit `{_fmt(seen_3)}`, unseen 2-digit `{_fmt(unseen_2)}`, "
            f"unseen 3-digit `{_fmt(unseen_3)}`. "
            f"Length gap `{_fmt(length_gap)}`, composition-combo gap `{_fmt(combo_gap)}`."
        )
    best_unseen = max(
        (
            _get_final_nem(result, "c_unseen_combo_familiar_length") or 0.0
            for result in analysis.values()
        ),
        default=0.0,
    )
    if best_unseen < 0.3:
        lines.append(
            "- Systematic unseen-composition generalization is still poor, so the next step should be explicit rule-following / RFFT-like curriculum rather than a new architecture."
        )
    return lines


def _get_final_nem(result: dict[str, Any], split_name: str) -> float | None:
    if split_name not in result:
        return None
    return result[split_name].get("overall", {}).get("final_normalized_exact_match")


def _empty_metrics() -> dict[str, Any]:
    return {
        "count": 0,
        "final_normalized_exact_match": 0.0,
        "empty_prediction_rate": 0.0,
        "false_answer_rate": 0.0,
        "avg_tokens_generated": 0.0,
        "per_digit_accuracy": 0.0,
        "units_accuracy": 0.0,
        "tens_accuracy": 0.0,
        "hundreds_accuracy": 0.0,
        "carry_prediction_accuracy": 0.0,
    }


def _case_from_record(record: dict[str, Any]) -> AdditionCase:
    return AdditionCase(a=int(record["metadata"]["a"]), b=int(record["metadata"]["b"]))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _space_digits(value: str) -> str:
    return " ".join(value)


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
