"""Compare M-33.6e production artifacts with explicit host-bound receipts."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336e_comparison import (
    compare_m336e_production_trees,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh M-33.6e production comparison exists")
    report = compare_m336e_production_trees(args.windows, args.karina)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if report["status"] != "PASS":
        raise SystemExit("platform-neutral M-33.6e production artifacts differ")


if __name__ == "__main__":
    main()
