from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ai_brain.data.answer_format import ANSWER_FORMAT_NAMES
from ai_brain.data.generators import GENERATION_PROFILES, GENERATOR_NAMES
from ai_brain.data.presets import TASK_PRESETS, get_task_preset, resolve_task_selection
from ai_brain.data.writer import (
    dataset_stats,
    generate_arithmetic_primitive_split,
    generate_data_split,
    generate_jsonl,
    generate_range_ablation,
    generate_range_primed,
)
from ai_brain.eval.compare import compare_evals
from ai_brain.eval.diagnostics import analyze_eval
from ai_brain.eval.runner import eval_lm, generate_answer
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.trainer import train_tokenizer
from ai_brain.model.config import MODEL_CONFIG_NAMES, get_named_model_config
from ai_brain.model.factory import build_model, model_class_name
from ai_brain.model.smoke import run_model_smoke_step
from ai_brain.model.utils import count_parameters, format_parameter_count
from ai_brain.runtime.device import (
    format_device_info,
    get_device_info,
    run_smoke_train_step,
)
from ai_brain.training.config import LOSS_MODES, TrainConfig
from ai_brain.training.lm_dataset import prepare_lm_dataset
from ai_brain.training.loop import train_lm

RANGE_PRIMED_RECIPES: dict[str, dict[str, float | str]] = {
    "quantity_direct": {
        "shifted_prime_fraction": 0.10,
        "answer_format": "place_role_numeric",
    },
    "state_change": {
        "shifted_prime_fraction": 0.10,
        "answer_format": "place_role_numeric",
    },
    "sorting_short": {
        "shifted_prime_fraction": 0.20,
        "answer_format": "normal_answer",
    },
    "arithmetic": {
        "shifted_prime_fraction": 0.50,
        "answer_format": "scratchpad",
    },
}


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _compact_task_rows(rows: list[dict]) -> list[dict]:
    keep_keys = (
        "task_type",
        "count",
        "normalized_exact_match",
        "final_normalized_exact_match",
        "false_answer_rate",
        "empty_prediction_rate",
        "delta_normalized_exact_match",
        "left_count",
        "right_count",
        "left_normalized_exact_match",
        "right_normalized_exact_match",
        "delta_final_normalized_exact_match",
        "left_final_normalized_exact_match",
        "right_final_normalized_exact_match",
    )
    return [{key: row[key] for key in keep_keys if key in row} for row in rows]


def _compact_analyze_eval_result(result: dict) -> dict:
    diagnostics = result["diagnostics"]
    return {
        "output_dir": result["output_dir"],
        "diagnostics_path": result["diagnostics_path"],
        "markdown_path": result["markdown_path"],
        "overall": diagnostics["overall"],
        "worst_task_types": _compact_task_rows(diagnostics["worst_task_types"]),
        "best_task_types": _compact_task_rows(diagnostics["best_task_types"]),
        "suspicious_task_types": _compact_task_rows(
            diagnostics["suspicious_task_types"]
        ),
    }


def _compact_compare_evals_result(result: dict) -> dict:
    comparison = result["comparison"]
    return {
        "output_dir": result["output_dir"],
        "comparison_path": result["comparison_path"],
        "markdown_path": result["markdown_path"],
        "left_label": comparison["left_label"],
        "right_label": comparison["right_label"],
        "overall": comparison["overall"],
        "most_improved_task_types": _compact_task_rows(
            comparison["most_improved_task_types"]
        ),
        "most_regressed_task_types": _compact_task_rows(
            comparison["most_regressed_task_types"]
        ),
        "still_failed_task_types": _compact_task_rows(
            comparison["still_failed_task_types"]
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-brain",
        description="Development CLI for the AI Brain project.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    device_parser = subparsers.add_parser(
        "device",
        help="Show runtime device information.",
    )
    device_parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU instead of CUDA.",
    )

    smoke_parser = subparsers.add_parser(
        "smoke",
        help="Run a tiny forward/backward/optimizer training step.",
    )
    smoke_parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU instead of CUDA.",
    )
    smoke_parser.add_argument(
        "--seed",
        type=int,
        default=1234,
        help="Random seed for the smoke training step.",
    )

    model_info_parser = subparsers.add_parser(
        "model-info",
        help="Show model parameter information.",
    )
    model_info_parser.add_argument(
        "--config",
        choices=MODEL_CONFIG_NAMES,
        default="tiny",
        help="Model config to inspect.",
    )

    model_smoke_parser = subparsers.add_parser(
        "model-smoke",
        help="Run a tiny Transformer forward/backward/optimizer step.",
    )
    model_smoke_parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU instead of CUDA.",
    )
    model_smoke_parser.add_argument(
        "--config",
        choices=MODEL_CONFIG_NAMES,
        default="debug",
        help="Model config to use.",
    )
    model_smoke_parser.add_argument(
        "--seed",
        type=int,
        default=1234,
        help="Random seed for the model smoke step.",
    )
    model_smoke_parser.add_argument(
        "--batch-size",
        type=int,
        default=2,
        help="Batch size for the model smoke step.",
    )
    model_smoke_parser.add_argument(
        "--sequence-length",
        type=int,
        default=16,
        help="Sequence length for the model smoke step.",
    )

    generate_data_parser = subparsers.add_parser(
        "generate-data",
        help="Generate a synthetic JSONL training dataset.",
    )
    generate_data_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSONL file path.",
    )
    generate_data_parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of examples to generate.",
    )
    generate_data_parser.add_argument(
        "--seed",
        type=int,
        default=1234,
        help="Random seed for deterministic generation.",
    )
    generate_data_parser.add_argument(
        "--task-type",
        action="append",
        choices=GENERATOR_NAMES,
        help="Restrict generation to one task type. Can be repeated.",
    )
    generate_data_parser.add_argument(
        "--task-preset",
        help="Restrict generation to a focused task preset.",
    )
    generate_data_parser.add_argument(
        "--profile",
        choices=tuple(GENERATION_PROFILES),
        help="Difficulty profile for generated examples.",
    )
    generate_data_parser.add_argument(
        "--answer-format",
        choices=ANSWER_FORMAT_NAMES,
        default="normal_answer",
        help="Answer/prompt formatting ablation for generated examples.",
    )

    generate_split_parser = subparsers.add_parser(
        "generate-data-split",
        help="Generate train/eval JSONL files and a dataset manifest.",
    )
    generate_split_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for train.jsonl, eval.jsonl, and manifest.json.",
    )
    generate_split_parser.add_argument(
        "--train-count",
        type=int,
        default=50_000,
        help="Number of training examples to generate.",
    )
    generate_split_parser.add_argument(
        "--eval-count",
        type=int,
        default=5_000,
        help="Number of eval examples to generate.",
    )
    generate_split_parser.add_argument(
        "--train-seed",
        type=int,
        default=1000,
        help="Random seed for the train split.",
    )
    generate_split_parser.add_argument(
        "--eval-seed",
        type=int,
        default=2000,
        help="Random seed for the eval split.",
    )
    generate_split_parser.add_argument(
        "--task-type",
        action="append",
        choices=GENERATOR_NAMES,
        help="Restrict generation to one task type. Can be repeated.",
    )
    generate_split_parser.add_argument(
        "--task-preset",
        help="Restrict generation to a focused task preset.",
    )
    generate_split_parser.add_argument(
        "--train-profile",
        choices=tuple(GENERATION_PROFILES),
        help="Difficulty profile for the train split.",
    )
    generate_split_parser.add_argument(
        "--eval-profile",
        choices=tuple(GENERATION_PROFILES),
        help="Difficulty profile for the eval split.",
    )
    generate_split_parser.add_argument(
        "--answer-format",
        choices=ANSWER_FORMAT_NAMES,
        default="normal_answer",
        help="Answer/prompt formatting ablation for generated examples.",
    )

    range_ablation_parser = subparsers.add_parser(
        "generate-range-ablation",
        help="Generate train_same/eval_same/eval_shifted JSONL files and manifest.",
    )
    range_ablation_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for train_same.jsonl, eval_same.jsonl, eval_shifted.jsonl, and manifest.json.",
    )
    range_ablation_parser.add_argument(
        "--train-count",
        type=int,
        required=True,
        help="Number of train_same examples to generate.",
    )
    range_ablation_parser.add_argument(
        "--eval-count",
        type=int,
        help="Number of examples for both eval_same and eval_shifted.",
    )
    range_ablation_parser.add_argument(
        "--eval-same-count",
        type=int,
        help="Number of eval_same examples to generate.",
    )
    range_ablation_parser.add_argument(
        "--eval-shifted-count",
        type=int,
        help="Number of eval_shifted examples to generate.",
    )
    range_ablation_parser.add_argument(
        "--train-seed",
        type=int,
        required=True,
        help="Random seed for train_same.",
    )
    range_ablation_parser.add_argument(
        "--eval-same-seed",
        type=int,
        required=True,
        help="Random seed for eval_same.",
    )
    range_ablation_parser.add_argument(
        "--eval-shifted-seed",
        type=int,
        required=True,
        help="Random seed for eval_shifted.",
    )
    range_ablation_parser.add_argument(
        "--task-type",
        action="append",
        choices=GENERATOR_NAMES,
        help="Restrict generation to one task type. Can be repeated.",
    )
    range_ablation_parser.add_argument(
        "--task-preset",
        help="Restrict generation to a focused task preset.",
    )
    range_ablation_parser.add_argument(
        "--train-profile",
        choices=tuple(GENERATION_PROFILES),
        default="train_same",
        help="Difficulty profile for train_same.",
    )
    range_ablation_parser.add_argument(
        "--eval-same-profile",
        choices=tuple(GENERATION_PROFILES),
        default="eval_same",
        help="Difficulty profile for eval_same.",
    )
    range_ablation_parser.add_argument(
        "--eval-shifted-profile",
        choices=tuple(GENERATION_PROFILES),
        default="eval_shifted",
        help="Difficulty profile for eval_shifted.",
    )
    range_ablation_parser.add_argument(
        "--answer-format",
        choices=ANSWER_FORMAT_NAMES,
        default="normal_answer",
        help="Answer/prompt formatting ablation for generated examples.",
    )

    range_primed_parser = subparsers.add_parser(
        "generate-range-primed",
        help="Generate train/train_same/train_shifted_prime and four eval splits.",
    )
    range_primed_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for primed train/eval JSONL files and manifest.json.",
    )
    range_primed_parser.add_argument(
        "--train-count",
        type=int,
        required=True,
        help="Total train examples across train_same and train_shifted_prime.",
    )
    range_primed_parser.add_argument(
        "--eval-count",
        type=int,
        help="Number of examples for each eval split.",
    )
    range_primed_parser.add_argument(
        "--eval-same-count",
        type=int,
        help="Number of eval_same examples to generate.",
    )
    range_primed_parser.add_argument(
        "--eval-shifted-in-distribution-count",
        type=int,
        help="Number of eval_shifted_in_distribution examples to generate.",
    )
    range_primed_parser.add_argument(
        "--eval-shifted-holdout-count",
        type=int,
        help="Number of eval_shifted_holdout examples to generate.",
    )
    range_primed_parser.add_argument(
        "--eval-far-shifted-count",
        type=int,
        help="Number of eval_far_shifted examples to generate.",
    )
    range_primed_parser.add_argument(
        "--train-same-seed",
        type=int,
        required=True,
        help="Random seed for train_same.",
    )
    range_primed_parser.add_argument(
        "--train-shifted-prime-seed",
        type=int,
        required=True,
        help="Random seed for train_shifted_prime.",
    )
    range_primed_parser.add_argument(
        "--eval-same-seed",
        type=int,
        required=True,
        help="Random seed for eval_same.",
    )
    range_primed_parser.add_argument(
        "--eval-shifted-in-distribution-seed",
        type=int,
        required=True,
        help="Random seed for eval_shifted_in_distribution.",
    )
    range_primed_parser.add_argument(
        "--eval-shifted-holdout-seed",
        type=int,
        required=True,
        help="Random seed for eval_shifted_holdout.",
    )
    range_primed_parser.add_argument(
        "--eval-far-shifted-seed",
        type=int,
        required=True,
        help="Random seed for eval_far_shifted.",
    )
    range_primed_parser.add_argument(
        "--shifted-prime-fraction",
        type=float,
        help="Fraction of train examples drawn from train_shifted_prime.",
    )
    range_primed_parser.add_argument(
        "--task-type",
        action="append",
        choices=GENERATOR_NAMES,
        help="Restrict generation to one task type. Can be repeated.",
    )
    range_primed_parser.add_argument(
        "--task-preset",
        help="Restrict generation to a focused task preset.",
    )
    range_primed_parser.add_argument(
        "--train-same-profile",
        choices=tuple(GENERATION_PROFILES),
        default="train_same",
        help="Difficulty profile for train_same.",
    )
    range_primed_parser.add_argument(
        "--train-shifted-prime-profile",
        choices=tuple(GENERATION_PROFILES),
        default="train_shifted_prime",
        help="Difficulty profile for train_shifted_prime.",
    )
    range_primed_parser.add_argument(
        "--eval-same-profile",
        choices=tuple(GENERATION_PROFILES),
        default="eval_same",
        help="Difficulty profile for eval_same.",
    )
    range_primed_parser.add_argument(
        "--eval-shifted-in-distribution-profile",
        choices=tuple(GENERATION_PROFILES),
        default="eval_shifted_in_distribution",
        help="Difficulty profile for eval_shifted_in_distribution.",
    )
    range_primed_parser.add_argument(
        "--eval-shifted-holdout-profile",
        choices=tuple(GENERATION_PROFILES),
        default="eval_shifted_holdout",
        help="Difficulty profile for eval_shifted_holdout.",
    )
    range_primed_parser.add_argument(
        "--eval-far-shifted-profile",
        choices=tuple(GENERATION_PROFILES),
        default="eval_far_shifted",
        help="Difficulty profile for eval_far_shifted.",
    )
    range_primed_parser.add_argument(
        "--answer-format",
        choices=ANSWER_FORMAT_NAMES,
        help="Answer/prompt formatting. Defaults to the M-12 recipe for --task-preset.",
    )

    arithmetic_primitive_parser = subparsers.add_parser(
        "generate-arithmetic-primitive",
        help="Generate controlled arithmetic primitive train/eval splits.",
    )
    arithmetic_primitive_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for train/eval JSONL files and manifest.json.",
    )
    arithmetic_primitive_parser.add_argument(
        "--primitive",
        required=True,
        choices=tuple(
            name
            for name in TASK_PRESETS
            if name
            in {
                "digit_add_carry",
                "digit_sub_borrow",
                "add_2digit_no_carry",
                "add_2digit_with_carry",
                "sub_2digit_no_borrow",
                "sub_2digit_with_borrow",
                "missing_addend_simple",
                "compare_sum_simple",
                "double_step_simple",
            }
        ),
        help="Arithmetic primitive preset to generate.",
    )
    arithmetic_primitive_parser.add_argument(
        "--train-count",
        type=int,
        required=True,
        help="Number of train_same examples.",
    )
    arithmetic_primitive_parser.add_argument(
        "--eval-count",
        type=int,
        help="Number of examples for each eval split.",
    )
    arithmetic_primitive_parser.add_argument("--eval-same-count", type=int)
    arithmetic_primitive_parser.add_argument(
        "--eval-shifted-in-distribution-count",
        type=int,
    )
    arithmetic_primitive_parser.add_argument(
        "--eval-holdout-digit-combinations-count",
        type=int,
    )
    arithmetic_primitive_parser.add_argument("--eval-far-range-count", type=int)
    arithmetic_primitive_parser.add_argument("--train-seed", type=int, required=True)
    arithmetic_primitive_parser.add_argument(
        "--eval-same-seed", type=int, required=True
    )
    arithmetic_primitive_parser.add_argument(
        "--eval-shifted-in-distribution-seed",
        type=int,
        required=True,
    )
    arithmetic_primitive_parser.add_argument(
        "--eval-holdout-digit-combinations-seed",
        type=int,
        required=True,
    )
    arithmetic_primitive_parser.add_argument(
        "--eval-far-range-seed",
        type=int,
        required=True,
    )
    arithmetic_primitive_parser.add_argument(
        "--answer-format",
        choices=ANSWER_FORMAT_NAMES,
        default="compact_digit_trace",
        help="Answer format for generated examples.",
    )

    dataset_stats_parser = subparsers.add_parser(
        "dataset-stats",
        help="Show counts and prompt statistics for a JSONL dataset.",
    )
    dataset_stats_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input JSONL file path.",
    )
    dataset_stats_parser.add_argument(
        "--task-type",
        action="append",
        choices=GENERATOR_NAMES,
        help="Expected task type. Can be repeated. Defaults to all known types.",
    )
    dataset_stats_parser.add_argument(
        "--top-duplicates",
        type=int,
        default=20,
        help="Maximum number of duplicate prompt records to include.",
    )

    train_tokenizer_parser = subparsers.add_parser(
        "train-tokenizer",
        help="Train a byte-level BPE tokenizer from text or JSONL datasets.",
    )
    train_tokenizer_parser.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        help="Input .jsonl or text file. Can be repeated.",
    )
    train_tokenizer_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output tokenizer JSON file path.",
    )
    train_tokenizer_parser.add_argument(
        "--vocab-size",
        type=int,
        default=8192,
        help="Target tokenizer vocabulary size.",
    )
    train_tokenizer_parser.add_argument(
        "--min-frequency",
        type=int,
        default=2,
        help="Minimum pair frequency for BPE merges.",
    )

    tokenizer_info_parser = subparsers.add_parser(
        "tokenizer-info",
        help="Show tokenizer vocabulary and special token information.",
    )
    tokenizer_info_parser.add_argument(
        "--tokenizer",
        type=Path,
        required=True,
        help="Tokenizer JSON file path.",
    )

    encode_text_parser = subparsers.add_parser(
        "encode-text",
        help="Encode text with a trained tokenizer.",
    )
    encode_text_parser.add_argument(
        "--tokenizer",
        type=Path,
        required=True,
        help="Tokenizer JSON file path.",
    )
    encode_text_parser.add_argument(
        "--text",
        required=True,
        help="Text to encode.",
    )

    decode_ids_parser = subparsers.add_parser(
        "decode-ids",
        help="Decode comma-separated token ids with a trained tokenizer.",
    )
    decode_ids_parser.add_argument(
        "--tokenizer",
        type=Path,
        required=True,
        help="Tokenizer JSON file path.",
    )
    decode_ids_parser.add_argument(
        "--ids",
        required=True,
        help="Comma-separated token ids.",
    )

    prepare_lm_parser = subparsers.add_parser(
        "prepare-lm-dataset",
        help="Tokenize a supervised LM JSONL dataset into a torch cache.",
    )
    prepare_lm_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input JSONL dataset path.",
    )
    prepare_lm_parser.add_argument(
        "--tokenizer",
        type=Path,
        required=True,
        help="Tokenizer JSON file path.",
    )
    prepare_lm_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output .pt cache path.",
    )
    prepare_lm_parser.add_argument(
        "--sequence-length",
        type=int,
        default=256,
        help="Fixed token sequence length.",
    )
    prepare_lm_parser.add_argument(
        "--loss-mode",
        choices=LOSS_MODES,
        default="answer-only",
        help="Labeling mode for supervised LM loss.",
    )
    prepare_lm_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild cache even when metadata matches.",
    )

    train_lm_parser = subparsers.add_parser(
        "train-lm",
        help="Train the baseline supervised causal LM.",
    )
    train_lm_parser.add_argument(
        "--train",
        type=Path,
        required=True,
        help="Training JSONL dataset path.",
    )
    train_lm_parser.add_argument(
        "--eval",
        type=Path,
        required=True,
        help="Eval JSONL dataset path.",
    )
    train_lm_parser.add_argument(
        "--tokenizer",
        type=Path,
        required=True,
        help="Tokenizer JSON file path.",
    )
    train_lm_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Run output directory.",
    )
    train_lm_parser.add_argument(
        "--config",
        choices=MODEL_CONFIG_NAMES,
        default="debug",
        help="Model architecture preset.",
    )
    train_lm_parser.add_argument(
        "--steps",
        type=int,
        default=200,
        help="Number of optimizer steps.",
    )
    train_lm_parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Training batch size.",
    )
    train_lm_parser.add_argument(
        "--sequence-length",
        type=int,
        default=256,
        help="Fixed token sequence length.",
    )
    train_lm_parser.add_argument(
        "--loss-mode",
        choices=LOSS_MODES,
        default="answer-only",
        help="Supervised LM loss mode.",
    )
    train_lm_parser.add_argument(
        "--learning-rate",
        type=float,
        default=3e-4,
        help="AdamW learning rate.",
    )
    train_lm_parser.add_argument(
        "--seed",
        type=int,
        default=1234,
        help="Random seed.",
    )
    train_lm_parser.add_argument(
        "--grad-clip-norm",
        type=float,
        default=1.0,
        help="Maximum gradient norm for clipping.",
    )
    train_lm_parser.add_argument(
        "--eval-every",
        type=int,
        default=50,
        help="Evaluate every N steps.",
    )
    train_lm_parser.add_argument(
        "--eval-batches",
        type=int,
        default=20,
        help="Number of batches per eval pass.",
    )
    train_lm_parser.add_argument(
        "--save-every",
        type=int,
        default=100,
        help="Save checkpoint every N steps.",
    )
    train_lm_parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("cache/tokenized"),
        help="Directory for tokenized dataset caches.",
    )
    train_lm_parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU instead of CUDA.",
    )

    generate_answer_parser = subparsers.add_parser(
        "generate-answer",
        help="Generate one deterministic answer from a trained LM checkpoint.",
    )
    generate_answer_parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Model checkpoint path.",
    )
    generate_answer_parser.add_argument(
        "--tokenizer",
        type=Path,
        required=True,
        help="Tokenizer JSON file path.",
    )
    generate_answer_parser.add_argument(
        "--prompt",
        required=True,
        help="Prompt text to answer.",
    )
    generate_answer_parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=32,
        help="Maximum number of tokens to generate.",
    )
    generate_answer_parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU instead of CUDA.",
    )

    eval_lm_parser = subparsers.add_parser(
        "eval-lm",
        help="Run exact-answer generation benchmark for a checkpoint.",
    )
    eval_lm_parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Model checkpoint path.",
    )
    eval_lm_parser.add_argument(
        "--eval",
        type=Path,
        required=True,
        help="Eval JSONL dataset path.",
    )
    eval_lm_parser.add_argument(
        "--tokenizer",
        type=Path,
        required=True,
        help="Tokenizer JSON file path.",
    )
    eval_lm_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for predictions.jsonl and summary.json.",
    )
    eval_lm_parser.add_argument(
        "--max-examples",
        type=int,
        default=None,
        help="Maximum number of eval examples to run.",
    )
    eval_lm_parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=32,
        help="Maximum number of tokens to generate per example.",
    )
    eval_lm_parser.add_argument(
        "--seed",
        type=int,
        default=1234,
        help="Random seed for deterministic setup.",
    )
    eval_lm_parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU instead of CUDA.",
    )

    analyze_eval_parser = subparsers.add_parser(
        "analyze-eval",
        help="Analyze eval-lm predictions and write diagnostics reports.",
    )
    analyze_eval_parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="predictions.jsonl path produced by eval-lm.",
    )
    analyze_eval_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for diagnostics.json and diagnostics.md.",
    )
    analyze_eval_parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of top/worst/best records to include.",
    )
    analyze_eval_parser.add_argument(
        "--max-samples-per-task",
        type=int,
        default=10,
        help="Maximum error/correct samples stored per task type.",
    )

    compare_evals_parser = subparsers.add_parser(
        "compare-evals",
        help="Compare two eval-lm summary.json files.",
    )
    compare_evals_parser.add_argument(
        "--left-summary",
        type=Path,
        required=True,
        help="Left summary.json path.",
    )
    compare_evals_parser.add_argument(
        "--right-summary",
        type=Path,
        required=True,
        help="Right summary.json path.",
    )
    compare_evals_parser.add_argument(
        "--left-label",
        default="left",
        help="Human label for the left eval.",
    )
    compare_evals_parser.add_argument(
        "--right-label",
        default="right",
        help="Human label for the right eval.",
    )
    compare_evals_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for comparison.json and comparison.md.",
    )

    return parser


def _resolve_task_selection_or_exit(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> tuple[list[str] | None, str | None]:
    try:
        return resolve_task_selection(
            task_preset=args.task_preset,
            task_types=args.task_type,
        )
    except ValueError as error:
        parser.error(str(error))


def _range_primed_recipe_value(
    task_preset: str | None,
    key: str,
    fallback: float | str,
) -> float | str:
    if task_preset is None:
        return fallback
    return RANGE_PRIMED_RECIPES.get(task_preset, {}).get(key, fallback)


def _default_generate_profile(task_preset: str | None) -> str:
    if task_preset is None:
        return "train"
    return TASK_PRESETS[task_preset].default_profile


def _default_train_profile(task_preset: str | None) -> str:
    if task_preset is None:
        return "train"
    return TASK_PRESETS[task_preset].default_train_profile


def _default_eval_profile(task_preset: str | None) -> str:
    if task_preset is None:
        return "eval"
    return TASK_PRESETS[task_preset].default_eval_profile


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "device":
        info = get_device_info(prefer_cuda=not args.cpu)
        print(format_device_info(info))
        return 0

    if args.command == "smoke":
        info = get_device_info(prefer_cuda=not args.cpu)
        result = run_smoke_train_step(info, seed=args.seed)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "model-info":
        config = get_named_model_config(args.config)
        model = build_model(config)
        parameter_count = count_parameters(model)
        trainable_parameter_count = count_parameters(model, trainable_only=True)

        result = {
            "model": model_class_name(config),
            "model_type": config.model_type,
            "config_name": args.config,
            "parameters": parameter_count,
            "parameters_human": format_parameter_count(parameter_count),
            "trainable_parameters": trainable_parameter_count,
            "trainable_parameters_human": format_parameter_count(
                trainable_parameter_count
            ),
            "config": {
                "vocab_size": config.vocab_size,
                "max_sequence_length": config.max_sequence_length,
                "d_model": config.d_model,
                "num_layers": config.num_layers,
                "num_heads": config.num_heads,
                "ffn_hidden_dim": config.ffn_hidden_dim,
                "dropout": config.dropout,
                "tie_embeddings": config.tie_embeddings,
                "input_layers": config.input_layers,
                "recurrent_layers": config.recurrent_layers,
                "recurrent_cycles": config.recurrent_cycles,
                "output_layers": config.output_layers,
            },
        }

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "model-smoke":
        info = get_device_info(prefer_cuda=not args.cpu)
        result = run_model_smoke_step(
            info,
            config_name=args.config,
            seed=args.seed,
            batch_size=args.batch_size,
            sequence_length=args.sequence_length,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "generate-data":
        task_types, task_preset = _resolve_task_selection_or_exit(parser, args)
        profile = args.profile or _default_generate_profile(task_preset)
        result = generate_jsonl(
            output_path=args.output,
            count=args.count,
            seed=args.seed,
            task_types=task_types,
            profile=profile,
            task_preset=task_preset,
            answer_format=args.answer_format,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "generate-data-split":
        task_types, task_preset = _resolve_task_selection_or_exit(parser, args)
        train_profile = args.train_profile or _default_train_profile(task_preset)
        eval_profile = args.eval_profile or _default_eval_profile(task_preset)
        result = generate_data_split(
            output_dir=args.output_dir,
            train_count=args.train_count,
            eval_count=args.eval_count,
            train_seed=args.train_seed,
            eval_seed=args.eval_seed,
            task_types=task_types,
            train_profile=train_profile,
            eval_profile=eval_profile,
            task_preset=task_preset,
            answer_format=args.answer_format,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "generate-range-ablation":
        task_types, task_preset = _resolve_task_selection_or_exit(parser, args)
        eval_same_count = (
            args.eval_same_count
            if args.eval_same_count is not None
            else args.eval_count
        )
        eval_shifted_count = (
            args.eval_shifted_count
            if args.eval_shifted_count is not None
            else args.eval_count
        )
        if eval_same_count is None or eval_shifted_count is None:
            parser.error(
                "generate-range-ablation requires --eval-count or both "
                "--eval-same-count and --eval-shifted-count."
            )
        result = generate_range_ablation(
            output_dir=args.output_dir,
            train_count=args.train_count,
            eval_same_count=eval_same_count,
            eval_shifted_count=eval_shifted_count,
            train_seed=args.train_seed,
            eval_same_seed=args.eval_same_seed,
            eval_shifted_seed=args.eval_shifted_seed,
            task_types=task_types,
            train_profile=args.train_profile,
            eval_same_profile=args.eval_same_profile,
            eval_shifted_profile=args.eval_shifted_profile,
            task_preset=task_preset,
            answer_format=args.answer_format,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "generate-range-primed":
        task_types, task_preset = _resolve_task_selection_or_exit(parser, args)
        eval_same_count = (
            args.eval_same_count
            if args.eval_same_count is not None
            else args.eval_count
        )
        eval_shifted_in_distribution_count = (
            args.eval_shifted_in_distribution_count
            if args.eval_shifted_in_distribution_count is not None
            else args.eval_count
        )
        eval_shifted_holdout_count = (
            args.eval_shifted_holdout_count
            if args.eval_shifted_holdout_count is not None
            else args.eval_count
        )
        eval_far_shifted_count = (
            args.eval_far_shifted_count
            if args.eval_far_shifted_count is not None
            else args.eval_count
        )
        if (
            eval_same_count is None
            or eval_shifted_in_distribution_count is None
            or eval_shifted_holdout_count is None
            or eval_far_shifted_count is None
        ):
            parser.error(
                "generate-range-primed requires --eval-count or all four "
                "specific eval count arguments."
            )
        shifted_prime_fraction = (
            args.shifted_prime_fraction
            if args.shifted_prime_fraction is not None
            else float(
                _range_primed_recipe_value(
                    task_preset,
                    "shifted_prime_fraction",
                    0.10,
                )
            )
        )
        answer_format = args.answer_format or str(
            _range_primed_recipe_value(task_preset, "answer_format", "normal_answer")
        )
        result = generate_range_primed(
            output_dir=args.output_dir,
            train_count=args.train_count,
            eval_same_count=eval_same_count,
            eval_shifted_in_distribution_count=eval_shifted_in_distribution_count,
            eval_shifted_holdout_count=eval_shifted_holdout_count,
            eval_far_shifted_count=eval_far_shifted_count,
            train_same_seed=args.train_same_seed,
            train_shifted_prime_seed=args.train_shifted_prime_seed,
            eval_same_seed=args.eval_same_seed,
            eval_shifted_in_distribution_seed=args.eval_shifted_in_distribution_seed,
            eval_shifted_holdout_seed=args.eval_shifted_holdout_seed,
            eval_far_shifted_seed=args.eval_far_shifted_seed,
            shifted_prime_fraction=shifted_prime_fraction,
            task_types=task_types,
            train_same_profile=args.train_same_profile,
            train_shifted_prime_profile=args.train_shifted_prime_profile,
            eval_same_profile=args.eval_same_profile,
            eval_shifted_in_distribution_profile=(
                args.eval_shifted_in_distribution_profile
            ),
            eval_shifted_holdout_profile=args.eval_shifted_holdout_profile,
            eval_far_shifted_profile=args.eval_far_shifted_profile,
            task_preset=task_preset,
            answer_format=answer_format,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "generate-arithmetic-primitive":
        preset = get_task_preset(args.primitive)
        eval_same_count = (
            args.eval_same_count
            if args.eval_same_count is not None
            else args.eval_count
        )
        eval_shifted_in_distribution_count = (
            args.eval_shifted_in_distribution_count
            if args.eval_shifted_in_distribution_count is not None
            else args.eval_count
        )
        eval_holdout_digit_combinations_count = (
            args.eval_holdout_digit_combinations_count
            if args.eval_holdout_digit_combinations_count is not None
            else args.eval_count
        )
        eval_far_range_count = (
            args.eval_far_range_count
            if args.eval_far_range_count is not None
            else args.eval_count
        )
        if (
            eval_same_count is None
            or eval_shifted_in_distribution_count is None
            or eval_holdout_digit_combinations_count is None
            or eval_far_range_count is None
        ):
            parser.error(
                "generate-arithmetic-primitive requires --eval-count or all four "
                "specific eval count arguments."
            )
        result = generate_arithmetic_primitive_split(
            output_dir=args.output_dir,
            train_count=args.train_count,
            eval_same_count=eval_same_count,
            eval_shifted_in_distribution_count=eval_shifted_in_distribution_count,
            eval_holdout_digit_combinations_count=(
                eval_holdout_digit_combinations_count
            ),
            eval_far_range_count=eval_far_range_count,
            train_seed=args.train_seed,
            eval_same_seed=args.eval_same_seed,
            eval_shifted_in_distribution_seed=(args.eval_shifted_in_distribution_seed),
            eval_holdout_digit_combinations_seed=(
                args.eval_holdout_digit_combinations_seed
            ),
            eval_far_range_seed=args.eval_far_range_seed,
            task_types=preset.task_types,
            task_preset=preset.name,
            answer_format=args.answer_format,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "dataset-stats":
        result = dataset_stats(
            input_path=args.input,
            expected_task_types=args.task_type,
            top_duplicate_limit=args.top_duplicates,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "train-tokenizer":
        result = train_tokenizer(
            input_paths=args.input,
            output_path=args.output,
            vocab_size=args.vocab_size,
            min_frequency=args.min_frequency,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "tokenizer-info":
        tokenizer = ByteLevelBpeTokenizer.load(args.tokenizer)
        result = {"tokenizer_path": str(args.tokenizer), **tokenizer.info()}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "encode-text":
        tokenizer = ByteLevelBpeTokenizer.load(args.tokenizer)
        ids = tokenizer.encode(args.text)
        result = {"ids": ids, "count": len(ids)}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "decode-ids":
        ids = [int(token_id) for token_id in args.ids.split(",") if token_id.strip()]
        tokenizer = ByteLevelBpeTokenizer.load(args.tokenizer)
        text = tokenizer.decode(ids, skip_special_tokens=False)
        result = {"text": text, "count": len(ids)}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "prepare-lm-dataset":
        result = prepare_lm_dataset(
            input_path=args.input,
            tokenizer_path=args.tokenizer,
            output_path=args.output,
            sequence_length=args.sequence_length,
            loss_mode=args.loss_mode,
            force=args.force,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "train-lm":
        result = train_lm(
            TrainConfig(
                train_path=args.train,
                eval_path=args.eval,
                tokenizer_path=args.tokenizer,
                output_dir=args.output_dir,
                model_config_name=args.config,
                steps=args.steps,
                batch_size=args.batch_size,
                sequence_length=args.sequence_length,
                loss_mode=args.loss_mode,
                learning_rate=args.learning_rate,
                grad_clip_norm=args.grad_clip_norm,
                seed=args.seed,
                eval_every=args.eval_every,
                eval_batches=args.eval_batches,
                save_every=args.save_every,
                cache_dir=args.cache_dir,
                cpu=args.cpu,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "generate-answer":
        result = generate_answer(
            checkpoint_path=args.checkpoint,
            tokenizer_path=args.tokenizer,
            prompt=args.prompt,
            max_new_tokens=args.max_new_tokens,
            cpu=args.cpu,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "eval-lm":
        result = eval_lm(
            checkpoint_path=args.checkpoint,
            eval_path=args.eval,
            tokenizer_path=args.tokenizer,
            output_dir=args.output_dir,
            max_examples=args.max_examples,
            max_new_tokens=args.max_new_tokens,
            seed=args.seed,
            cpu=args.cpu,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "analyze-eval":
        result = analyze_eval(
            predictions_path=args.predictions,
            output_dir=args.output_dir,
            top_k=args.top_k,
            max_samples_per_task=args.max_samples_per_task,
        )
        print(
            json.dumps(
                _compact_analyze_eval_result(result),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "compare-evals":
        result = compare_evals(
            left_summary_path=args.left_summary,
            right_summary_path=args.right_summary,
            left_label=args.left_label,
            right_label=args.right_label,
            output_dir=args.output_dir,
        )
        print(
            json.dumps(
                _compact_compare_evals_result(result),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
