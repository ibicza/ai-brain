import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.benchmark_v2 import (
    run_m281_benchmark,
    write_m281_benchmark,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_m281_benchmark(
        ChemistryDomainService.open(args.root), calculation_count=args.count
    )
    if args.output:
        write_m281_benchmark(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
