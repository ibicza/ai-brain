"""Verify the exact E16 -> F17 -> H17 -> E17 M-33.6b release."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    verify_m336b_git_freeze_protocol,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--f17-sha", required=True)
    parser.add_argument("--h17-sha", required=True)
    parser.add_argument("--e17-sha", required=True)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify_m336b_git_freeze_protocol(
        args.repository.resolve(strict=True),
        f17_sha=args.f17_sha,
        h17_sha=args.h17_sha,
        e17_sha=args.e17_sha,
        upstream=args.upstream,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(asdict(report)) + "\n", encoding="utf-8", newline="\n"
    )
    if not report.passed:
        raise SystemExit("M-33.6b exact freeze verification failed")


if __name__ == "__main__":
    main()
