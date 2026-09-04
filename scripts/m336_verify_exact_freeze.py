"""Print the post-commit exact-Git M-33.6 freeze verification receipt."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    verify_m336_git_freeze_protocol,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--f15-sha", required=True)
    parser.add_argument("--h15-sha", required=True)
    parser.add_argument("--e15-sha", required=True)
    parser.add_argument("--upstream", required=True)
    args = parser.parse_args()
    report = verify_m336_git_freeze_protocol(
        args.repository,
        f15_sha=args.f15_sha,
        h15_sha=args.h15_sha,
        e15_sha=args.e15_sha,
        upstream=args.upstream,
    )
    print(canonical_json(asdict(report)))
    if not report.passed:
        raise SystemExit("M-33.6 exact Git freeze verification failed")


if __name__ == "__main__":
    main()
