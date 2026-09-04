"""Build the genuine M-33.6d pool from allowed metadata-only probes."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336d_final_pipeline import probe_metadata_pool


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r19-sha", required=True)
    parser.add_argument("--windows-cache", type=Path, required=True)
    parser.add_argument("--karina-cache", type=Path, required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--host", required=True)
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
    if head != args.r19_sha or len(head) != 40 or status:
        raise ValueError("metadata probe requires a clean exact-R19 worktree")
    if args.output.exists():
        raise FileExistsError("fresh metadata output already exists")
    pool, receipts, scenarios = probe_metadata_pool(
        windows_cache=_load(args.windows_cache),
        karina_cache=_load(args.karina_cache),
        timestamp=args.timestamp,
        host=args.host,
    )
    args.output.mkdir(parents=True)
    _write(args.output / "candidate_pool.json", pool)
    _write(args.output / "metadata_receipts.json", receipts)
    _write(args.output / "failure_simulation.json", scenarios)


if __name__ == "__main__":
    main()
