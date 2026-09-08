"""Derive a public M-33.6j implementation-lineage receipt from live Git."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_lineage import (
    build_m336j_implementation_lineage_policy,
    verify_m336j_implementation_lineage,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336J lineage output must be fresh")
    policy = build_m336j_implementation_lineage_policy(args.expected_sha)
    receipt = verify_m336j_implementation_lineage(
        args.repository, args.git_executable, policy
    )
    write_canonical_json(args.output, asdict(receipt))


if __name__ == "__main__":
    main()
