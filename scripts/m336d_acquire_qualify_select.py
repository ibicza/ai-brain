"""Execute the sole M-33.6d global acquisition and selector invocation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    acquire_qualify_select_once,
)


def _worktrees(repository: Path) -> tuple[Path, ...]:
    output = subprocess.run(
        ("git", "worktree", "list", "--porcelain"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(
        Path(line.removeprefix("worktree "))
        for line in output.splitlines()
        if line.startswith("worktree ")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--authority-statement", type=Path, required=True)
    parser.add_argument("--f19-sha", required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--host", required=True)
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
    if head != args.f19_sha or len(head) != 40 or status:
        raise ValueError("acquisition requires a clean exact-F19 worktree")
    pool = json.loads(args.pool.read_text(encoding="utf-8"))
    acquire_qualify_select_once(
        pool=pool,
        vault_root=args.vault,
        public_output=args.public_output,
        authority_statement=args.authority_statement,
        f19_sha=args.f19_sha,
        timestamp=args.timestamp,
        host=args.host,
        git_worktrees=_worktrees(repository),
    )


if __name__ == "__main__":
    main()
