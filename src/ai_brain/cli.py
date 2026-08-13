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

    parser.error(f"Unknown command: {args.command}")
    return 2
