from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.scale_v2 import run_m261_scale_regression


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the M-26.1 v2 compatibility scale regression"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--v1-10k-root", type=Path, required=True)
    parser.add_argument("--v1-100k-root", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=500)
    args = parser.parse_args()
    result = run_m261_scale_regression(
        args.output_dir,
        v1_roots={10_000: args.v1_10k_root, 100_000: args.v1_100k_root},
        samples=args.samples,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
