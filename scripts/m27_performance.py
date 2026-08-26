from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.router.performance import benchmark_fact_response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fact-root", type=Path, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--predicate", required=True)
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark_fact_response(
        args.fact_root,
        subject=args.subject,
        predicate_id=args.predicate,
        samples=args.samples,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
