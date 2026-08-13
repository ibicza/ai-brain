from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from ai_brain.model.config import tiny_config
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

        print(
            json.dumps(
                {
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
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
