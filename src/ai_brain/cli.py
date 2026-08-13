from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from ai_brain.data.generators import GENERATION_PROFILES, GENERATOR_NAMES
from ai_brain.data.writer import dataset_stats, generate_data_split, generate_jsonl
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.trainer import train_tokenizer
from ai_brain.model.config import tiny_config
from ai_brain.model.smoke import run_model_smoke_step
from ai_brain.model.tiny_transformer import TinyCausalTransformer
from ai_brain.model.utils import count_parameters, format_parameter_count
from ai_brain.runtime.device import (
    format_device_info,
    get_device_info,
    run_smoke_train_step,
)
from ai_brain.training.config import LOSS_MODES, TrainConfig
from ai_brain.training.lm_dataset import prepare_lm_dataset
from ai_brain.training.loop import train_lm


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

    subparsers.add_parser(
        "model-info",
        help="Show tiny model parameter information.",
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
        choices=["debug", "tiny"],
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
        "--profile",
        choices=tuple(GENERATION_PROFILES),
        default="train",
        help="Difficulty profile for generated examples.",
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
        "--train-profile",
        choices=tuple(GENERATION_PROFILES),
        default="train",
        help="Difficulty profile for the train split.",
    )
    generate_split_parser.add_argument(
        "--eval-profile",
        choices=tuple(GENERATION_PROFILES),
        default="eval",
        help="Difficulty profile for the eval split.",
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
        choices=["debug", "tiny"],
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
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
        config = tiny_config()
        model = TinyCausalTransformer(config)
        parameter_count = count_parameters(model)
        trainable_parameter_count = count_parameters(model, trainable_only=True)

        result = {
            "model": "TinyCausalTransformer",
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
        result = generate_jsonl(
            output_path=args.output,
            count=args.count,
            seed=args.seed,
            task_types=args.task_type,
            profile=args.profile,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "generate-data-split":
        result = generate_data_split(
            output_dir=args.output_dir,
            train_count=args.train_count,
            eval_count=args.eval_count,
            train_seed=args.train_seed,
            eval_seed=args.eval_seed,
            task_types=args.task_type,
            train_profile=args.train_profile,
            eval_profile=args.eval_profile,
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

    parser.error(f"Unknown command: {args.command}")
    return 2
