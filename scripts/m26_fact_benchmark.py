from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.benchmark import (
    generate_synthetic_corpus,
    run_scale_benchmark,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M-26 synthetic corpus and scale benchmark"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--claims", type=int)
    parser.add_argument("--sizes", type=int, nargs="+")
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=26000)
    args = parser.parse_args()
    if args.claims is not None:
        result = generate_synthetic_corpus(
            args.output_dir, claim_count=args.claims, seed=args.seed
        )
    else:
        result = run_scale_benchmark(
            args.output_dir,
            sizes=tuple(args.sizes or (1_000, 10_000, 100_000)),
            samples=args.samples,
            seed=args.seed,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
