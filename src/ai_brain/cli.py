from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    prefer_cuda = not args.cpu
    info = get_device_info(prefer_cuda=prefer_cuda)

    if args.command == "device":
        print(format_device_info(info))
        return 0

    if args.command == "smoke":
        result = run_smoke_train_step(info, seed=args.seed)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
