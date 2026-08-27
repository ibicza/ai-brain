import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.benchmark import run_benchmark, write_benchmark
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--count", type=int, default=10_000)
    args = parser.parse_args()
    report = run_benchmark(
        ChemistryDomainService.open(args.root), calculation_count=args.count
    )
    if args.output:
        write_benchmark(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
