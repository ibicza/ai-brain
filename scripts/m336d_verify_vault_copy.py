"""Verify a transferred M-33.6d vault against its public hash manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336d_final_pipeline import verify_vault_copy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh vault comparison output exists")
    output = subprocess.run(
        ("git", "worktree", "list", "--porcelain"),
        cwd=args.repository.resolve(strict=True),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    worktrees = tuple(
        Path(line.removeprefix("worktree "))
        for line in output.splitlines()
        if line.startswith("worktree ")
    )
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = verify_vault_copy(
        args.vault.resolve(strict=True), manifest, git_worktrees=worktrees
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    if report["difference_count"]:
        raise SystemExit("vault transfer differs")


if __name__ == "__main__":
    main()
