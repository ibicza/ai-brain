"""Exercise every declared M-33.6e public producer against contract v2."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336e_contracts import (
    M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    ProducerContractCompatibilityGate,
    m336e_future_public_producers,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--legacy-acquisition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != args.expected_head or len(head) != 40 or status:
        raise ValueError("contract gate requires a clean exact worktree")
    if args.output.exists():
        raise FileExistsError("fresh producer-contract report already exists")
    legacy = json.loads(args.legacy_acquisition.read_text(encoding="utf-8"))
    report = ProducerContractCompatibilityGate(
        M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
        m336e_future_public_producers(legacy),
    ).run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(asdict(report)) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
