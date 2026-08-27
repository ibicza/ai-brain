from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.benchmark_v3 import (
    run_m282_benchmark,
    write_m282_benchmark,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M-28.2 provenance benchmark")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_m282_benchmark(
        ChemistryDomainService.open(args.root), calculation_count=args.count
    )
    if args.output:
        write_m282_benchmark(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
